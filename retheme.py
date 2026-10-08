import re

with open("frontend/src/index.css", "r", encoding="utf-8") as f:
    css = f.read()

replacements = {
    # Root vars (the old ones were replaced to --brand- by powershell, but let's redefine the block)
    r"--brand-950: #063d2b;": "--brand-950: #290029;",
    r"--brand-900: #07553a;": "--brand-900: #420042;",
    r"--brand-700: #087a4c;": "--brand-700: #6b006b;",
    r"--brand-600: #079455;": "--brand-600: #820082;", # Wema Purple
    r"--brand-100: #dff7e9;": "--brand-100: #faebfa;",
    r"--brand-50: #eefbf3;": "--brand-50: #fdf5fd;",
    
    # Neutral tints (shifting from green-tinted grays to purple-tinted grays)
    r"--ink: #15201b;": "--ink: #1c1520;",
    r"--muted: #69756f;": "--muted: #736975;",
    r"--line: #e5ebe7;": "--line: #ebe5eb;",
    r"--canvas: #f7f9f7;": "--canvas: #f9f7f9;",
    
    # Shadows & borders & hardcoded gradients
    r"#07945533": "#82008233", # btn-primary shadow
    r"#c7ead6": "#e6b3e6", # btn-secondary border
    r"#dff7e9, #a8e1bd": "#faebfa, #e6b3e6", # hero-banner gradient
    r"#3e6352": "#573157", # hero-copy p
    r"#063d2b33": "#29002933", # floating-price shadow
    r"#172b200a": "#2b172b0a", # product-card shadow
    r"#4dca78": "#ba4dba", # progress-fill gradient end
    r"#eef4ef": "#f4eef4", # category-row span
    r"#193d2a0a": "#3d193d0a", # search-box shadow
    r"#10291c1c": "#2910291c", # sticky-action shadow
    r"#dff7e9, #c2edd1": "#faebfa, #e8c2e8", # groups-hero gradient
    r"#426353": "#5c355c", # groups-hero p
    r"#79dda0": "#dda0dd", # splash logo span
    r"#65da91": "#da65da", # splash loader
    r"#21cc6b": "#cc21b0", # status dot searching
    r"#b3dfc4": "#dfb3df", # processing mark
    r"#e7eee9": "#eee7ee", # progress track bg
    r"#98a19c": "#a198a1", # price row s
    r"#cce7d5": "#e7cce7", # retail price border
    r"#d7e3db": "#e3d7e3", # buyer faces
    r"#f4f7f5": "#f7f4f7", # info callout bg
    r"#f0f4f1": "#f4f0f4", # round icon bg
    r"#ccd5cf": "#d5cccd", # total line border
    r"#bfc9c2": "#c9bfc9", # radio empty
    r"#9aa39e": "#a39aa3", # state page small
    r"#d3e5da": "#e5d3e5", # tracking progress
    r"#dbe2dd": "#e2dbdd", # timeline item
    r"#cfd7d2": "#d7cfd2", # timeline item span
    r"#f3f5f4": "#f5f3f5", # support link bg
    r"#b5cec2": "#ceb5ce", # profile stats span
    r"#9ba49f": "#a49ba4", # profile menu svg
    
    # AI elements - shift blue/purples to fit better with Wema if needed, but they are already purple!
    # I'll leave --purple as is, or slightly tweak it if it clashes. It's fine.
    
    # Avatar - shift from orange to something matching Wema
    r"#f2cbb8": "#f2b8e6",
    r"#5e2d1d": "#5e1d4b",
}

for old, new in replacements.items():
    css = css.replace(old, new)

with open("frontend/src/index.css", "w", encoding="utf-8") as f:
    f.write(css)
print("CSS updated successfully!")
