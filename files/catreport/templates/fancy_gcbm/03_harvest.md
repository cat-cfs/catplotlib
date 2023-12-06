---
jupytext:
  formats: md:myst
  text_representation:
    extension: .md
    format_name: myst
kernelspec:
  display_name: Python 3
  language: python
  name: python3
---

```{code-cell} ipython3
:tags: ["remove-cell"]

from report_config import *
from util import *

%store -r providers
%store -r provider_paths
```

### Harvest

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
%matplotlib inline

for title, path in provider_paths.items():
    print(title)
    with connect(path) as gcbm_results_db:
        gcbm_harvest = pd.read_sql_query(
            f"""
            SELECT
                years.year,
                COALESCE(harvest_area_ha, 0) AS harvest_area_ha,
                COALESCE(harvest_tc, 0) AS harvest_tc,
                COALESCE(harvest_mtc, 0) AS harvest_mtc
            FROM (SELECT DISTINCT year FROM v_age_indicators) AS years
            LEFT JOIN (
                SELECT
                    harvest_area.year,
                    harvest_area_ha,
                    harvest_tc,
                    harvest_tc / 1e6 AS harvest_mtc
                FROM (
                    SELECT year, SUM(dist_area) AS harvest_area_ha
                    FROM v_total_disturbed_areas
                    WHERE disturbance_code IN ({','.join('?' * len(harvest_dist_codes))})
                    GROUP BY year
                ) AS harvest_area
                LEFT JOIN (
                    SELECT year, SUM(flux_tc) AS harvest_tc
                    FROM v_flux_indicator_aggregates
                    WHERE indicator = 'All Production'
                    GROUP BY year
                ) AS harvest_carbon
                    ON harvest_area.year = harvest_carbon.year
            ) AS fluxes
                ON years.year = fluxes.year
            ORDER BY years.year
            """, gcbm_results_db, params=tuple(harvest_dist_codes)
        )

        ax_area = None
        ax_carbon = None
        ax_density = None
        ax_cumulative = None
        ax_cumulative_area = None
        data_table = pd.DataFrame({"year": []}).set_index("year")
            
        gcbm_harvest["harvest_tc_per_ha"] = gcbm_harvest["harvest_tc"] / gcbm_harvest["harvest_area_ha"]

        df_area = (
            gcbm_harvest[["year", "harvest_area_ha"]]
            .set_index("year")
            .fillna(0)
            .astype(int)
        )

        ax_area = df_area.plot(
            title=f"Harvest area",
            xlabel="Year", ylabel="ha / yr", ax=ax_area
        )

        df_carbon = (
            gcbm_harvest[["year", "harvest_mtc"]]
            .set_index("year")
            .fillna(0)
        )

        ax_carbon = df_carbon.plot(
            title=f"Carbon to products from harvest",
            xlabel="Year", ylabel="Mt C / yr", ax=ax_carbon
        )

        df_density = (
            gcbm_harvest[["year", "harvest_tc_per_ha"]]
            .set_index("year")
            .fillna(0)
        )

        ax_density = df_density.plot(
            title=f"Carbon to products per hectare harvest",
            xlabel="Year", ylabel="t C / ha / yr", ax=ax_density
        )

        df_cumulative = (
            gcbm_harvest[["year", "harvest_mtc"]]
            .set_index("year")
            .fillna(0)
            .cumsum()
        )

        ax_cumulative = df_cumulative.plot(
            title=f"Cumulative carbon to products from harvest",
            xlabel="Year", ylabel="Mt C", ax=ax_cumulative
        )

        df_cumulative_area = (
            gcbm_harvest[["year", "harvest_area_ha"]]
            .set_index("year")
            .fillna(0)
            .cumsum()
        ) / 1e6

        ax_cumulative_area = df_cumulative_area.plot(
            title=f"Cumulative harvest area",
            xlabel="Year", ylabel="M ha", ax=ax_cumulative_area
        )

        for (df, column, name) in (
            (df_area, "harvest_area_ha", "Clearcut Area (ha)"),
            (df_carbon, "harvest_mtc", "Clearcut Harvest (Mt C)"),
            (df_density, "harvest_tc_per_ha", "Clearcut Harvest Density (tC / ha)"),
            (df_cumulative, "harvest_mtc", "Cumulative Clearcut Harvest (Mt C)"),
            (df_cumulative_area, "harvest_area_ha", "Cumulative Clearcut Area (M ha)")
        ):
            data_table = data_table.join(df[[column]].rename(columns={column: name}), how="outer")

        for ax in (ax_area, ax_carbon, ax_density, ax_cumulative, ax_cumulative_area):
            _ = ax.legend()
            add_figure_id("03", ax)

        plt.show()
        display_or_dump(data_table.rename_axis("Year").fillna(0), f"03_{title}_harvest")
```
