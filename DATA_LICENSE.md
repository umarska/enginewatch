# Dataset attribution and terms

EngineWatch uses **NASA C-MAPSS FD001**, a simulated turbofan-engine degradation benchmark provided by the NASA Ames Prognostics Center of Excellence.

- Dataset record and download: https://doi.org/10.5281/zenodo.15346912
- Publisher: NASA Diagnostics and Prognostics Group
- Creator: National Aeronautics and Space Administration
- Dataset licence in the publisher's API metadata: **Creative Commons Attribution 4.0 International (CC BY 4.0)**
- Machine-readable licence field: https://zenodo.org/api/records/15346912 (`metadata.license.id = cc-by-4.0`, verified 5 October 2026)
- Licence text: https://creativecommons.org/licenses/by/4.0/
- Original NASA catalogue: https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data

The NASA catalogue lists its licence as unspecified, and the rendered Zenodo page does not display the licence value. The linked Zenodo API metadata is the source for the CC BY 4.0 designation; do not mistake EngineWatch's MIT code licence for the dataset's terms.

Please acknowledge the original work:

> A. Saxena, K. Goebel, D. Simon, and N. Eklund. "Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation." Proceedings of the First International Conference on Prognostics and Health Management, 2008.

The download script verifies the archive MD5 `79a22f36e80606c69d0e9e4da5bb2b7a` and records SHA-256 fingerprints in `artifacts/provenance.json`. The complete raw archive is downloaded locally and excluded from Git.

The included example CSV reproduces test engine 1's readings. Demo histories, prediction tables, charts, and trained model are generated from FD001 through the transformations documented in `docs/methods.md`. Those changes and original-data attribution are preserved here. The source data is simulated; EngineWatch does not assert that it represents measurements from an operational aircraft fleet.

EngineWatch's original software source is covered by the separate [MIT licence](LICENSE).
