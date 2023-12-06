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

### Wildfire emissions

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
%matplotlib inline

for title, path in provider_paths.items():
    print(title)
    with connect(path) as gcbm_results_db:
        wildfire_fluxes = pd.read_sql_query(
            f"""
            SELECT
                years.year,
                COALESCE(dom_flux_mtco2e, 0) AS dom_flux_mtco2e,
                COALESCE(bio_flux_mtco2e, 0) AS bio_flux_mtco2e
            FROM (SELECT DISTINCT year FROM v_age_indicators) AS years
            LEFT JOIN (
                SELECT
                    year,
                    SUM(
                        CASE
                            WHEN indicator = 'DOMCOEmission' THEN flux_tc * {co2e_multiplier}
                            WHEN indicator = 'DOMCO2Emission'
                                THEN (flux_tc * {co2e_multiplier})
                                   + (flux_tc * {n2o_multiplier} * {co2e_multiplier})
                            WHEN indicator = 'DOMCH4Emission' THEN flux_tc * {ch4_multiplier}
                        END
                    ) / 1e6 AS dom_flux_mtco2e,
                    SUM(
                        CASE
                            WHEN indicator = 'BioCOEmission' THEN flux_tc * {co2e_multiplier}
                            WHEN indicator = 'BioCO2Emission'
                                THEN (flux_tc * {co2e_multiplier})
                                   + (flux_tc * {n2o_multiplier} * {co2e_multiplier})
                            WHEN indicator = 'BioCH4Emission' THEN flux_tc * {ch4_multiplier}
                        END
                    ) / 1e6 AS bio_flux_mtco2e
                FROM v_flux_indicators
                WHERE disturbance_code IN ({','.join('?' * len(wildfire_dist_codes))})
                    AND indicator IN (
                        'BioCOEmission', 'BioCO2Emission', 'BioCH4Emission',
                        'DOMCOEmission', 'DOMCO2Emission', 'DOMCH4Emission'
                    )
                GROUP BY year
            ) AS fluxes
                ON years.year = fluxes.year
            ORDER BY years.year
            """, gcbm_results_db, params=tuple(wildfire_dist_codes)
        )

        ax = None
        styles = ["b--", "b-"]
        ax = (
            wildfire_fluxes
            .set_index("year")
            .rename(columns={
                "dom_flux_mtco2e": f"DOM",
                "bio_flux_mtco2e": f"Bio"
            })
        ).plot(
            title=f"Wildfire emissions ({title})", xlabel="Year", ylabel="Mt CO2e / yr",
            style=styles, ax=ax
        )

        plt.legend(title=None)
        add_figure_id("01a")
        plt.show()

        total_wildfire_fluxes = wildfire_fluxes.groupby("year").sum().sum(axis=1)
        _ = total_wildfire_fluxes.plot(
            title="Wildfire emissions (total)",
            xlabel="Year", ylabel="Mt CO2e / yr"
        )

        add_figure_id("01a")
        plt.show()

        cumulative_total_wildfire_fluxes = total_wildfire_fluxes.cumsum()
        _ = cumulative_total_wildfire_fluxes.plot(
            title="Wildfire emissions (cumulative total)",
            xlabel="Year", ylabel="Mt CO2e"
        )

        add_figure_id("02")
        plt.show()

        data_table = pd.DataFrame({
            "Wildfire Emissions - Total (Mt CO2e)": total_wildfire_fluxes,
            "Wildfire Emissions - Cumulative Total (Mt CO2e)": cumulative_total_wildfire_fluxes
        })

        display_or_dump(data_table, f"02_{title}_wildfire_emissions")
```
