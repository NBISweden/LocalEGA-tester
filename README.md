[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Build Status](https://travis-ci.com/NBISweden/LocalEGA-tester.svg?branch=master)](https://travis-ci.com/NBISweden/LocalEGA-tester)
[![](https://images.microbadger.com/badges/image/nbisweden/localega-tester.svg)](https://microbadger.com/images/nbisweden/localega-tester "Get your own image badge on microbadger.com")

## End-to-end tester for LocalEGA

**NOTE: Requires Python >3.6.**
```
git clone https://github.com/NBISweden/LocalEGA-tester.git
pip install .
legatest -h
```

```
➜ legatest -h
usage: legatest [-h] input config

M4 end to end test with YAML configuration.

positional arguments:
  input       File to be uploaded.
  config      Configuration file.

optional arguments:
  -h, --help  show this help message and exit
```


### License

`LocalEGA-tester` and all it sources are released under GNU General Public License v3.0.