# Dependency and font notices

No third-party dependency source or font binaries are vendored here. Install from their official distributions and preserve their own notices if redistributing them. A repository license applies only to repository material the maintainer has the right to license.

Core dependencies:
- Pillow: HPND-style Pillow/PIL license. https://github.com/python-pillow/Pillow
- NumPy and SciPy: BSD-style licenses and bundled component notices. https://numpy.org/ and https://scipy.org/
- Matplotlib: Matplotlib license and bundled font notices, including DejaVu and STIX. https://matplotlib.org/stable/project/license.html
- fontTools: MIT license. https://github.com/fonttools/fonttools
- FFmpeg: LGPL/GPL configuration-dependent licensing; libx264 builds have additional GPL implications. Installed external executable, not redistributed here. https://ffmpeg.org/legal.html

Optional dependencies:
- SymPy 1.14.0: installed metadata declares BSD. Symbolic algebra gate; not vendored. https://sympy.org
- jsonschema 4.26.0: installed metadata declares MIT. Schema validation gate; not vendored. https://github.com/python-jsonschema/jsonschema
- Poppler: optional external PDF inspection/rasterization tools; review the exact distribution’s license before redistribution. https://poppler.freedesktop.org
- PyMuPDF: AGPL or commercial terms. Do not assume the repository license replaces those terms or permits any combined redistribution. https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright
- edge-tts: version 7.3.1 uses LGPLv3, except its MIT-licensed srt_composer.py; the remote service has separate terms and availability. https://github.com/rany2/edge-tts
- Noto CJK: SIL Open Font License 1.1. Download from the official project and retain its license when redistributing the fonts. https://github.com/notofonts/noto-cjk

These are dependency pointers, not a legal opinion or a claim that all versions have identical terms. Read the exact installed distributions' license files for release-specific obligations.

External parser boundary: Only a small optional import adapter is provided for MinerU 4.0.12 basic. The third-party package and weights are not automatically installed, vendored or redistributed here. Its version-specific code and individual model terms require separate review; do not assume a pure Apache/MIT license or blanket compatibility. No weights or parser service are part of the five-node release.
