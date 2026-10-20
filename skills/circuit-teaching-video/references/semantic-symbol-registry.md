# Stable semantic variable identities

`style/symbol-registry.json` holds explicit symbol IDs, mathematical atoms, roles and colors. The same resolved registry should drive equations, curves and labels. Unknown atoms remain neutral; added identities require an explicit mathematical atom, role and color. Avoid random color assignment and per-frame language-model choices.

The inherited defaults include transconductance, body transconductance, device output resistance, drain load, input resistance and transimpedance identities. They are a configurable circuit palette, not universal physical laws. The resistor-divider demo uses neutral unregistered atoms.

`rendering/semantic_math.py` tracks source-token identity through real MathText glyph nodes. Primed forms preserve their base identity, while operators and arithmetic powers remain neutral. Re-run geometry and pixel checks after typography changes.

Knowledge colors are not attention colors. Red focus/glow is removable and separate. Do not add a legend unless it helps the requested explanation.
