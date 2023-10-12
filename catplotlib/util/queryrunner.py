import urllib
import os
import logging
import shutil
import warnings
import re
import psutil
import pandas as pd
import numpy as np
import sqlalchemy as sql
from contextlib import contextmanager
from functools import partial
from numbers import Number
from glob import glob
from string import Formatter
from sqlalchemy import create_engine
from sqlalchemy import Column
from sqlalchemy import text
from sqlalchemy import bindparam
from sqlalchemy import MetaData
from sqlalchemy import Table
from sqlalchemy import select
from sqlalchemy import insert
from sqlalchemy import inspect
from sqlalchemy.types import NullType
from sqlalchemy.exc import SAWarning
from textwrap import indent
from textwrap import shorten

warnings.filterwarnings("ignore", category=SAWarning)

class QueryRunner:

    type_map = {
        np.float64: sql.Double,
        np.int64  : sql.Integer,
        np.object_: sql.String,
        np.str_   : sql.String
    }

    def __init__(self, config=None):
        self.config = config or {}
        self.classifiers = self.config.get("classifiers") or []

    def run(self, sql_path, target_db, output_db=None, new_table_append=False):
        '''
        Runs a set of queries located at sql_path in their natural order
        (i.e. alphabetical). Multiple SQL statements can be semicolon-delimited
        within the files.

        Parameters:
          sql_path - a directory containing at least one .sql file
          target_db - the database path(s) to run queries against directly or attach to
          output_db - if specified, queries are run against a new database with the target_db(s) attached
          new_table_append - if false, overwrite existing tables in output_db; if
            true, append to existing tables; if a dict, append to existing tables
            with an additional identifying column and label.
        '''
        if output_db:
            os.makedirs(os.path.dirname(output_db), exist_ok=True)
        
        working_db = "" if new_table_append else (output_db or target_db)
        if new_table_append:
            if not output_db:
                raise RuntimeError("output_db must be specified in new_table_append mode")
        else:
            if output_db and os.path.exists(output_db):
                os.remove(output_db)
        
        all_original_tables = set()
        target_dbs = target_db if isinstance(target_db, list) else [target_db]
        attach_target_db = output_db is not None
        with self.connect(working_db) as working_conn:
            if attach_target_db:
                for i, target in enumerate(target_dbs):
                    with self.connect(target) as target_conn:
                        target_tables = self.get_table_names(target_conn)
                        all_original_tables.update(target_tables)

                    working_conn.execute(text(f"ATTACH '{target}' AS other_{i}"))
                    for table in target_tables:
                        working_conn.execute(text(
                            f"CREATE TEMP VIEW IF NOT EXISTS {table} AS SELECT * FROM other_{i}.{table}"))
            
            sql_files = glob(rf"{sql_path}\*.sql") if os.path.isdir(sql_path) else [sql_path]    
            for sql_file in sql_files:
                self._run_queries(working_conn, sql_file)

            if new_table_append:
                with self.connect(output_db) as output_conn:
                    new_tables = self.get_table_names(working_conn) - all_original_tables
                    self.copy_tables(working_conn, output_conn, new_tables,
                                     new_table_append, new_table_append)

    def merge_databases(self, databases, output_path, source_col_name=None, *tables):
        '''
        Merges two databases with identical schemas together into a single output
        database. Each table gets an extra column identifying the source database
        for each row in the merged output.

        Parameters:
          databases - a dictionary of database title to SQLite file path
          output_path - the output database; will be deleted if it already exists
          tables - [optional] merge only the listed tables
        '''
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if os.path.exists(output_path):
            os.remove(output_path)
        
        with self.connect(output_path) as output_conn:
            for label, input_db_path in databases.items():
                with self.connect(input_db_path) as input_conn:
                    if not tables:
                        tables = self.get_table_names(input_conn)

                    self.copy_tables(
                        input_conn, output_conn, tables, True,
                        {source_col_name: label} if source_col_name else None)

    def copy_tables(self, from_conn, to_conn, tables, append=False, include_source_column=None):
        print(f"Copying tables: {', '.join(tables)}")
        if not isinstance(tables, dict):
            tables = dict(zip(tables, tables))

        md = MetaData()
        md.reflect(bind=from_conn, only=lambda table_name, _: table_name in tables.keys())
                
        original_md = MetaData()
        original_md.reflect(to_conn)
        
        output_md = MetaData()
        for fqn, table in md.tables.items():
            print(f"  {fqn}")
            new_table_name = tables[table.name]
            table.tometadata(output_md, schema=None, name=new_table_name)
            
            # Try an exact copy of the table schema - this might have some
            # undefined column data types from SQLite "CREATE TABLE AS ..."
            output_table = Table(new_table_name, output_md, extend_existing=True)
            for col in output_table.columns:
                if isinstance(col.type, NullType):
                    # If any column has a null type, fall back to inferring
                    # the column types from a sample of the table data.
                    table_data = from_conn.execute(select(table))
                    df = pd.DataFrame(table_data.fetchmany(size=100), columns=table_data.keys())
                    output_table = self._df_to_table(output_md, df, new_table_name)
                    break

            if include_source_column:
                source_col, source_name = \
                    next((k, v) for k, v in include_source_column.items())
                
                if source_col not in [col.name for col in output_table.columns]:
                    output_table.append_column(Column(source_col, sql.Text))

            if not append:
                output_table.drop(to_conn, checkfirst=True)

            # Note: for MS Access, requires sqlalchemy-access >= 2.0.2 for YESNO fields.
            output_table.indexes = set()
            output_table.create(to_conn, checkfirst=True)

            # Add any new columns to the existing table, if applicable.
            if new_table_name in original_md:
                original_table_columns = [c.name for c in original_md.tables[new_table_name].columns]
                for col in table.columns:
                    if col.name not in original_table_columns:
                        to_conn.execute(f"ALTER TABLE {new_table_name} ADD COLUMN {col.name} {col.type}")
            
            origin_data = {source_col: source_name} if include_source_column else None
            self._batch_insert(to_conn, output_table, from_conn.execute(select(table)),
                               lambda row: {k: v for k, v in row._mapping.items()}, origin_data)

    def import_tables(self, db_path, source_db, tables, append=False, include_source_column=None):
        with self.connect(source_db) as working_conn, \
        self.connect(db_path) as output_conn:
            self.copy_tables(working_conn, output_conn, tables, append, include_source_column)

    def import_xls(self, db_path, xls_path, table_name=None, append=False, cell_range=None, **kwargs):
        table_name = table_name or kwargs.get("sheet_name", "xls_import")
        if cell_range:
            kwargs.update(self._range_to_kwargs(cell_range))

        print(f"Importing {xls_path} into {table_name}...")
        df = pd.read_excel(xls_path, **kwargs)
        self._import_df(db_path, df, table_name, append)

    def import_csv(self, db_path, csv_path, table_name=None, columns=None, append=False):
        table_name = table_name or os.path.splitext(os.path.basename(csv_path))[0]
        print(f"Importing {csv_path} into {table_name}...")
        df = pd.read_csv(csv_path)
        if columns:
            self._replace_df_cols(df, columns)
            
        self._import_df(db_path, df, table_name, append)

    def import_sql(self, db_path, source_db, sql_path, append=False, include_source_column=None, table=None):
        with self.connect(source_db) as source_conn:
            sql_files = glob(rf"{sql_path}\*.sql") if os.path.isdir(sql_path) else [sql_path]
            for sql_file in sql_files:
                for i, sql in enumerate(self._load_sql(sql_file)):
                    table_name = table or os.path.splitext(os.path.basename(sql_file))[0]
                    if i > 0:
                        table_name = f"{table_name}_{i}"

                    query = text(sql)
                    query_params = query.compile().bind_names.values()
                    query = query.bindparams(*(
                        bindparam(param_name, required=False,
                                  expanding=True if isinstance(self.config[param_name], list)
                                            else False)
                        for param_name in query_params
                    ))

                    results = source_conn.execute(query.bindparams(**{
                        k: v for k, v in self.config.items() if k in query_params
                    }))
                    
                    df = pd.DataFrame(results.fetchall(), columns=results.keys())
                    if include_source_column:
                        source_col, source_name = \
                            next((k, v) for k, v in include_source_column.items())
                        
                        df[source_col] = source_name
                        
                    self._import_df(db_path, df, table_name, append)

    @contextmanager
    def connect(self, db_path):
        db_path = str(db_path)
        connection_url = "sqlite://"
        schema = None
        if db_path.startswith("postgresql"):
            # Raw SQLAlchemy string with an extra /schema on the end.
            connection_url, schema = db_path.rsplit("/", 1)
            schema = schema.lower()
        elif db_path.endswith(".db"):
            connection_url = f"sqlite:///{db_path}"
        elif db_path.endswith(".accdb") or db_path.endswith(".mdb"):
            if not os.path.exists(db_path):
                self._create_mdb(db_path)
        
            connection_string = (
                r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
                f"DBQ={os.path.abspath(db_path)};"
                r"ExtendedAnsiSQL=1;"
            )

            connection_url = \
                "access+pyodbc:///?odbc_connect={}" \
                .format(urllib.parse.quote_plus(connection_string))

        engine = create_engine(connection_url, future=True)
        with engine.connect() as conn:
            try:
                with conn.begin():
                    if "sqlite" in connection_url:
                        for sql in (
                            "PRAGMA journal_mode=WAL",
                            "PRAGMA synchronous=normal",
                            "PRAGMA page_size=4096",
                            "PRAGMA temp_store=2",
                            f"PRAGMA cache_size={int(psutil.virtual_memory().available / 4096 * 0.75)}"
                        ):
                            conn.execute(text(sql))
                    elif schema:
                        conn.execute(text(f"SET SEARCH_PATH={schema}"))
                
                    yield conn
                
                if "sqlite" in connection_url:
                    conn.execute(text("PRAGMA analysis_limit=1000"))
                    conn.execute(text("PRAGMA optimize"))
                
                conn.close()
            finally:
                engine.dispose()

    def get_table_names(self, conn, pattern=None, views=True):
        table_names = inspect(conn).get_table_names()
        if views:
            table_names += inspect(conn).get_view_names()
        
        if pattern:
            table_names = (t for t in table_names if pattern.lower() in t.lower())
        
        return set(table_names)

    def _create_mdb(self, path, overwrite=True):
        '''
        Creates an empty Access database.
        '''
        path = os.path.abspath(str(path))
        if os.path.exists(path):
            if overwrite:
                os.unlink(path)
            else:
                return
            
        dest_dir = os.path.dirname(path)
        os.makedirs(dest_dir, exist_ok=True)

        dsn = ";".join(("Provider=Microsoft.ACE.OLEDB.12.0",
                        "Jet OLEDB:Engine Type=5",
                        f"Data Source={path}"))
        
        import win32com.client
        catalog = win32com.client.Dispatch("ADOX.Catalog")
        catalog.Create(dsn)
        
    def _batch_insert(self, conn, table, data, row_extractor, extra_row_data=None):
        batch = []
        for i, row in enumerate(data, 1):
            row_data = row_extractor(row)
            if any((v is not None for v in row_data.values())):
                row_data.update(extra_row_data or {})
                batch.append(row_data)
                
            if i % 10000 == 0:
                conn.execute(insert(table), batch)
                print(f"    {i}...")
                batch = []
        
        if batch:
            print(f"    {i}")
            conn.execute(insert(table), batch)

    def _replace_df_cols(self, df, new_cols):
        if isinstance(new_cols, dict):
            df.columns = [new_cols.get(c,  c) for c in df.columns]
        else:
            if len(new_cols) != len(df.columns):
                raise RuntimeError(
                    f"Number of new column names does not match the number of "
                    "columns in the dataframe.")

            df.columns = new_cols

    def _df_to_table(self, md, df, table_name):
        columns = []
        for col, dtype in zip(df.columns, df.dtypes):
            if any((isinstance(value, str) for value in df[col])):
                dtype = np.dtype(np.str_)
            elif all((int(value) == value if isinstance(value, Number)
                     and not np.isnan(value) else False for value in df[col])):
                dtype = np.dtype(np.int64)

            columns.append(Column(col, QueryRunner.type_map[dtype.type]))

        table = Table(table_name, md, *columns, extend_existing=True)
        
        return table

    def _import_df(self, db_path, df, table_name, append=False):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        with self.connect(db_path) as conn:
            md = MetaData()
            table = self._df_to_table(md, df, table_name)
            if not append:
                table.drop(conn, checkfirst=True)

            print(f"Importing data into {table_name}")
            table.create(conn, checkfirst=True)
            self._batch_insert(conn, table, df.replace({np.nan: None}).values,
                               lambda row: dict(zip(df.columns, row)))

    def _load_sql(self, path, dialect=None):
        '''Loads SQL from a file and adds the simulation classifier columns if needed.'''
        if not os.path.exists(path):
            raise IOError(f"File not found: {path}")
        
        queries = []
        for sql in open(path, "r").read().split(";"):
            if sql and not sql.isspace():
                classifier_sql = {}
                sql_params = {key for _, key, _, _ in Formatter().parse(sql) if key}
                for param in sql_params:
                    if "classifiers" not in param:
                        continue
                    
                    # Query can contain format strings to be replaced by classifier names:
                    # classifiers_select[_<table name>]
                    # classifiers_join_<table1>_<table2>
                    parts = param.split("_")
                    if "select" in parts:
                        table = parts[2] if len(parts) == 3 else None
                        classifier_sql[param] = ", ".join(
                            (f"{table}.{c}" for c in self.classifiers)
                            if table else self.classifiers)
                    elif "join" in parts:
                        _, _, lhs_table, rhs_table = parts
                        if dialect == "sqlite":
                            classifier_sql[param] = " AND ".join((
                                f"{lhs_table}.{c} IS {rhs_table}.{c}"
                                for c in self.classifiers))
                        else:
                            classifier_sql[param] = " AND ".join((
                                f"({lhs_table}.{c} = {rhs_table}.{c}"
                                " OR ({lhs_table}.{c} IS NULL AND {rhs_table}.{c} IS NULL))"
                                for c in self.classifiers))
                
                queries.append(partial(sql.format, **classifier_sql)(**self.config))
        
        return queries
        
    def _run_queries(self, conn, sql_file):
        print(f"Running queries from {sql_file}...")
        for sql in self._load_sql(sql_file, conn.engine.dialect.name):
            query = text(sql)
            query_params = query.compile().bind_names.values()
            query = query.bindparams(*(
                bindparam(param_name, required=False,
                          expanding=True if isinstance(self.config[param_name], list)
                                    else False)
                for param_name in query_params
            ))

            logging.info(indent(f"SQL: {shorten(sql, width=250)}", '  '))
            conn.execute(query.bindparams(**{
                k: v for k, v in self.config.items() if k in query_params
            }))
    
    def _range_to_kwargs(self, cell_range):
        cell_regex = "([a-zA-Z]*)([0-9]*)"
        range_start, range_end = cell_range.split(":")
        start_col, start_row = re.findall(cell_regex, range_start)[0]
        start_row = int(start_row)
        end_col, end_row = re.findall(cell_regex, range_end)[0]
        end_row = int(end_row)

        kwargs = {
            "usecols": ":".join((start_col, end_col)),
            "skiprows": start_row - 1,
            "nrows": end_row - start_row + 1
        }
        
        return kwargs
