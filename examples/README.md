# Synthetic demonstration data

These are **invented mathematical curves**, not experimental measurements and not properties of titanium or any real material. They are included only to demonstrate the app. No research data or Instron-reported summary values are included.

Use **Show sample data** beside the sample-group selector. The three groups appear as **Ductile (sample)**, **Balanced (sample)** and **Strong (sample)** alongside your own data. No paths need changing, and nothing is copied into your data folder. The visibility setting is remembered. Fresh installations start with samples visible and a **Demo comparison** graph showing representative curves with individual specimens. Existing personal graphs are preserved; create a new graph and tick the sample groups to explore them. Hiding the samples excludes them from plots and tables but retains saved selections and exclusions for the next time they are shown.

The bundled source is tracked internally as a second, relative path (`./examples/data`) in the local ignored settings. It is not shown as another folder input. Your own `./data` and `./output` defaults and any custom choices stay independent. Group and specimen identities have a separate sample namespace, so a research group with the same filename cannot be mixed into a synthetic average.

Three groups contain three specimens each, with 301 points per specimen. CSV columns are time (s), engineering strain (%), and engineering stress (MPa); the second row carries units in the accepted export format. Only these nine CSVs are allowed through the repository's research-data ignore rules.

## How the curves were made

| Group | E (MPa) | Elastic-limit stress (MPa) | Peak stress (MPa) | Strain at peak | Terminal strain | Pre-break stress (MPa) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Demo_Ductile | 70000 | 270 | 420 | 0.13 | 0.28 | 270 |
| Demo_Balanced | 100000 | 450 | 620 | 0.085 | 0.19 | 370 |
| Demo_Strong | 120000 | 650 | 850 | 0.06 | 0.12 | 550 |

All values are invented inputs. The elastic-limit stress is **not** the calculated 0.2% offset yield strength.

With engineering strain `e` as a fraction, `ey = elastic_limit / E`. Stress is `E * e` through `ey`; then `elastic_limit + (peak - elastic_limit) * (1 - exp(-4*(e-ey)/(eu-ey))) / (1-exp(-4))` through the peak at `eu`. Afterwards it decreases as `peak - (peak - prebreak) * ((e-eu)/(ef-eu))^1.4`. The final point drops to 20% of pre-break stress. This is an illustrative shape, not a constitutive or fracture model.

Specimens 1/2/3 multiply the stress inputs by 0.98/1.00/1.02 and peak/terminal strains by 0.95/1.00/1.05. E is unchanged. Sampling uses 101 points from 0 to 0.01 strain, 120 further points to the peak, and 80 further points to terminal strain; time is `e / 0.001`. Values are stored to six decimal places. There is no randomness, external source, fitted research curve, or implied measurement precision.

Personal graph edits are saved in ignored `tensile_workbench.project.json`. Back this file up yourself if needed; updating the app will not version your personal definitions.
