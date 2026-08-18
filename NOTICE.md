# Notices

## Licensing

The **code** in this repository is licensed under the MIT License. See
[LICENSE](LICENSE).

The **evaluation dataset** in `data/reports/` is not covered by the MIT License.
It is released under [Creative Commons Attribution 4.0 International
(CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). Attribution details
are in [CITATION.cff](CITATION.cff); provenance and contents are described in
[data/reports/README.md](data/reports/README.md).

## Clinical use

**This is research code. It is not a medical device.**

It has not been clinically validated, it has not been assessed by any regulatory
body, and it must not be used to make clinical decisions or to generate documents
delivered to real patients without independent professional review.

The evaluation dataset was measured on a single synthetic clinical case. No claim
of statistical generality is made. See
[docs/results.md](docs/results.md) for what was measured, what was not, and which
published figures could not be reproduced from this repository alone.

## Data protection

The clinical case in `data/reports/` is synthetic. The patient does not exist,
the identifier `12345678Z` is a documentation placeholder, and no protected
health information is present. The healthcare institutions named in the reports
are real Spanish organisations used to give the scenario a plausible setting;
they had no involvement in this project and the case is not attributable to them.

## Third-party services

This project integrates with services operated by third parties — Idonia, Recog
and Google Gemini. It is not affiliated with, endorsed by, or sponsored by any of
them. Their names and trademarks belong to their respective owners, and are used
here only to identify the interfaces this software talks to.

Credentials for those services are never stored in this repository. See
[.env.example](.env.example).

## Models

The transformer backends download third-party models from the Hugging Face Hub at
runtime. Those models carry their own licences, which are not covered by this
repository's. See [docs/references.md](docs/references.md) for which models are
used and why.
