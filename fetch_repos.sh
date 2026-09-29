#!/bin/sh
# Fetch the 14 projects used in the study. Tarball download (git clone is
# blocked by the sandbox CA store, but codeload works).
set -e
mkdir -p data && cd data
fetch() {
  repo=$1; branch=$2; name=$3
  [ -d "$name" ] && { echo "skip $name"; return; }
  curl -sL -o /tmp/r.tgz "https://codeload.github.com/$repo/tar.gz/refs/heads/$branch"
  tar xzf /tmp/r.tgz && mv "$(ls -d $repo-*/ | head -1)" "$name"
  echo "ok $name"
}
fetch anyio/anyio              main      anyio
fetch psf/black                main      black
fetch pallets/click            main      click
fetch pallets/flask            main      flask
fetch pallets/itsdangerous     main      itsdangerous
fetch pallets/jinja            main      jinja
fetch python-jsonschema/jsonschema main  jsonschema
fetch pytest-dev/pytest        main      pytest
fetch psf/requests             main      requests
fetch pypa/setuptools          main      setuptools
fetch sphinx-doc/sphinx        master    sphinx
fetch tox-dev/tox              main      tox
fetch urllib3/urllib3          main      urllib3
fetch pallets/werkzeug         main      werkzeug
rm -f /tmp/r.tgz
