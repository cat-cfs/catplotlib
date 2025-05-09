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
from pathlib import Path
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
from sqlalchemy.schema import PrimaryKeyConstraint
from sqlalchemy.types import NullType
from sqlalchemy.exc import SAWarning
from sqlalchemy_access.base import COUNTER
from sqlalchemy_access.base import YESNO
from sqlalchemy_access.base import TINYINT
from sqlalchemy_access.base import LONGCHAR
from sqlalchemy.ext.compiler import compiles
from textwrap import indent
from textwrap import shorten

warnings.filterwarnings("ignore", category=SAWarning)

@compiles(YESNO)
def compile_boolean_types(element, compiler, **kw):
    return "INTEGER"

@compiles(COUNTER)
@compiles(TINYINT)
def compile_int_types(element, compiler, **kw):
    return "INTEGER"

@compiles(LONGCHAR)
def compile_str_types(element, compiler, **kw):
    return "VARCHAR"

class AccessDb:

    def __init__(self, conn, path):
        self.conn = conn
        self.path = path

    @contextmanager
    def begin(self):
        with self.conn.begin():
            yield self.conn
    
    def insert(self, table, batch):
        import win32com.client
        engine = win32com.client.Dispatch("DAO.DBEngine.120")
        db = engine.OpenDatabase(self.path)
        record_set = None
        try:
            record_set = db.OpenRecordset(table.name)
            column_names = list(batch[0].keys())
            fields = self._extract_fields(record_set, column_names)
            for row in batch:
                record_set.AddNew()
                for i, value in enumerate(row.values()):
                    if value is None or value == "":
                        continue
                
                    fields[i].Value = value
            
                record_set.Update()
        finally:
            if record_set:
                record_set.Close()
            
            db.Close()
        
    def _extract_fields(self, record_set, column_names):
        fields = []
        for name in column_names:
            fields.append(record_set.Fields[name])
        
        return fields


class GenericDb:

    def __init__(self, conn, schema=None):
        self.conn = conn
        self.schema = schema

    @contextmanager
    def begin(self):
        with self.conn.begin():
            if self.schema:
                self.conn.execute(text(f"SET SEARCH_PATH={self.schema}"))
        
            yield self.conn
    
    def insert(self, table, batch):
        with self.begin() as conn:
            conn.execute(insert(table), batch)


class SqliteDb:

    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def begin(self):
        with self.conn.begin():
            for sql in (
                "PRAGMA journal_mode=off",
                "PRAGMA synchronous=off",
                "PRAGMA page_size=4096",
                "PRAGMA shrink_memory",
                f"PRAGMA cache_size={int(psutil.virtual_memory().available / 4096 * 0.75)}"
            ):
                self.conn.execute(text(sql))
        
            yield self.conn
            
    def insert(self, table, batch):
        with self.begin() as conn:
            conn.execute(insert(table), batch)


class QueryRunner:

    type_map = {
        np.float64: sql.Double,
        np.int64  : sql.Integer,
        np.object_: sql.String,
        np.str_   : sql.String,
        COUNTER   : sql.Integer
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
        with self.connect(working_db) as working_db:
            with working_db.begin() as working_conn:
                if attach_target_db:
                    for i, target in enumerate(target_dbs):
                        with self.connect(target) as target_conn:
                            target_tables = self.get_table_names(target_conn.conn)
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
          databases - a dictionary of database title to database path
          output_path - the output database; will be deleted if it already exists
          tables - [optional] merge only the listed tables
        '''
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        if os.path.exists(output_path):
            os.remove(output_path)
        
        with self.connect(output_path) as output_db:
            for i, (label, input_db_path) in enumerate(databases.items(), 1):
                with self.connect(input_db_path) as input_db:
                    with input_db.begin() as input_conn:
                        if not tables:
                            tables = self.get_table_names(input_conn)

                        print(f"Merging {label} ({i}/{len(databases)})")
                        self.copy_tables(
                            input_conn, output_db, tables, True,
                            {source_col_name: label} if source_col_name else None)

    def copy_tables(
        self, from_conn, to_db, tables, append=False, include_source_column=None,
        constraints=False, views=False
    ):
        print(f"Copying tables: {', '.join(tables)}")
        if not isinstance(tables, dict):
            tables = dict(zip(tables, tables))

        md = MetaData()
        md.reflect(bind=from_conn, only=lambda table_name, _: table_name in tables.keys(), views=views)
        
        with to_db.begin() as to_conn:
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

            with to_db.begin() as to_conn:
                if not append:
                    output_table.drop(to_conn, checkfirst=True)

                if not constraints:
                    output_table.constraints = set()
                    output_table.indexes = set()
                    output_table.primary_key = PrimaryKeyConstraint()
                    for column in output_table.columns:
                        column.foreign_keys = set()
                        column.constraints = set()
                        column.unique = False
                        column.primary_key = False
                        column.nullable = True

                output_table.create(to_conn, checkfirst=True)

                # Add any new columns to the existing table, if applicable.
                if new_table_name in original_md:
                    original_table_columns = [c.name.lower() for c in original_md.tables[new_table_name].columns]
                    for col in table.columns:
                        if col.name.lower() not in original_table_columns:
                            to_conn.execute(text(f"ALTER TABLE {new_table_name} ADD COLUMN {col.name} {col.type}"))
            
            origin_data = {source_col: source_name} if include_source_column else None
            if from_conn.engine.name == "sqlite" and to_db.conn.engine.name == "duckdb":
                self._attach_insert_duckdb(from_conn, to_db, table, output_table, origin_data)
            elif from_conn.engine.name == "sqlite" and to_db.conn.engine.name == "sqlite":
                self._attach_insert(from_conn, to_db, table, output_table, origin_data)
            else:
                self._batch_insert(to_db, output_table, from_conn.execute(select(table)),
                                   lambda row: {k: v for k, v in row._mapping.items()}, origin_data)

    def import_tables(
        self, db_path, source_db, tables, append=False, include_source_column=None,
        constraints=False, views=False
    ):
        with self.connect(source_db) as working_db, \
        self.connect(db_path) as output_db:
            with working_db.begin() as working_conn:
                self.copy_tables(
                    working_conn, output_db, tables, append, include_source_column,
                    constraints, views)

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

    def import_sql(self, db_path, source_db, sql_path, append=False, include_source_column=None):
        with self.connect(source_db) as source_db:
            with source_db.begin() as source_conn:
                sql_files = glob(rf"{sql_path}\*.sql") if os.path.isdir(sql_path) else [sql_path]
                for sql_file in sql_files:
                    for i, sql in enumerate(self._load_sql(sql_file, source_db.conn.engine.dialect.name)):
                        table_name = os.path.splitext(os.path.basename(sql_file))[0]
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
        elif db_path.endswith(".duckdb"):
            connection_url = f"duckdb:///{db_path}"
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
                if "sqlite://" in connection_url:
                    yield SqliteDb(conn)
                elif "access" in connection_url:
                    yield AccessDb(conn, db_path)
                else:
                    yield GenericDb(conn, schema)
                
                if "sqlite://" in connection_url:
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
    
    def get_column_names(self, conn, table_name):
        return [c["name"] for c in inspect(conn).get_columns(table_name)]

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
        
    def _batch_insert(self, db, table, data, row_extractor, extra_row_data=None):
        batch = []
        for i, row in enumerate(data, 1):
            row_data = row_extractor(row)
            if any((v is not None for v in row_data.values())):
                row_data.update(extra_row_data or {})
                batch.append(row_data)
                
            if i % 10000 == 0:
                print(f"    {i}...")
                db.insert(table, batch)
                batch = []
        
        if batch:
            print(f"    {i}")
            db.insert(table, batch)

    def _attach_insert_duckdb(self, from_conn, to_db, from_table, to_table, origin_data=None):
        insert_sql = f"INSERT INTO {to_table.name} BY NAME (SELECT * FROM other.{from_table.name})"
        if origin_data:
            origin_col, origin_name = next(iter(origin_data.items()))
            insert_sql = (
                f"INSERT INTO {to_table.name} BY NAME "
                f"(SELECT *, '{origin_name}' AS {origin_col} FROM other.{from_table.name})"
            )
        
        with to_db.begin() as to_conn:
            source_db_path = str(from_conn.engine.url).split("///")[1]
            to_conn.execute(text(f"ATTACH '{source_db_path}' AS other (TYPE SQLITE)"))
            to_conn.execute(text(insert_sql))
            to_conn.execute(text("DETACH other"))

    def _attach_insert(self, from_conn, to_db, from_table, to_table, origin_data=None):
        cols = ",".join((c.name for c in from_table.columns))
        insert_sql = f"INSERT INTO {to_table.name} ({cols}) SELECT {cols} FROM other.{from_table.name}"
        if origin_data:
            origin_col, origin_name = next(iter(origin_data.items()))
            insert_sql = (
                f"INSERT INTO {to_table.name} ({cols}, {origin_col}) "
                f"SELECT {cols}, '{origin_name}' AS {origin_col} FROM other.{from_table.name}"
            )
        
        with to_db.begin() as to_conn:
            source_db_path = str(from_conn.engine.url).split("///")[1]
            to_conn.execute(text(f"ATTACH '{source_db_path}' AS other"))
            to_conn.execute(text(insert_sql))

        with to_db.begin() as to_conn:
            to_conn.execute(text("DETACH other"))

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
        with self.connect(db_path) as db:
            with db.begin() as conn:
                md = MetaData()
                table = self._df_to_table(md, df, table_name)
                if not append:
                    table.drop(conn, checkfirst=True)

                print(f"Importing data into {table_name}")
                table.create(conn, checkfirst=True)

            self._batch_insert(db, table, df.replace({np.nan: None}).values,
                               lambda row: dict(zip(df.columns, row)))

    def _load_sql(self, path, dialect=None):
        '''Loads SQL from a file and adds the simulation classifier columns if needed.'''
        if not os.path.exists(path):
            raise IOError(f"File not found: {path}")
        
        queries = []
        for sql in open(path, "r").read().split(";"):
            if sql and not sql.isspace():
                fmt_sql = {}
                sql_params = {key for _, key, _, _ in Formatter().parse(sql) if key}
                for param in sql_params:
                    if param == "case_start":
                        fmt_sql[param] = "IIF(" if dialect == "access" else "CASE WHEN"
                    elif param == "case_then":
                        fmt_sql[param] = "," if dialect == "access" else "THEN"
                    elif param == "case_else":
                        fmt_sql[param] = "," if dialect == "access" else "ELSE"
                    elif param == "case_end":
                        fmt_sql[param] = ")" if dialect == "access" else "END"
                    elif "classifiers" in param:
                        # Query can contain format strings to be replaced by classifier names:
                        # classifiers_select[_<table name>]
                        # classifiers_join_<table1>_<table2>
                        parts = param.split("_")
                        if "select" in parts:
                            table = parts[2] if len(parts) == 3 else None
                            fmt_sql[param] = ", ".join(
                                (f"{table}.{c}" for c in self.classifiers)
                                if table else self.classifiers)
                        elif "join" in parts:
                            _, _, lhs_table, rhs_table = parts
                            if dialect == "sqlite":
                                fmt_sql[param] = " AND ".join((
                                    f"{lhs_table}.{c} IS {rhs_table}.{c}"
                                    for c in self.classifiers))
                            else:
                                fmt_sql[param] = " AND ".join((
                                    f"({lhs_table}.{c} = {rhs_table}.{c}"
                                    " OR ({lhs_table}.{c} IS NULL AND {rhs_table}.{c} IS NULL))"
                                    for c in self.classifiers))
                
                queries.append(partial(sql.format, **fmt_sql)(**self.config))
        
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
