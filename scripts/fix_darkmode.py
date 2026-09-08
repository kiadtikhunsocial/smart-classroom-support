# -*- coding: utf-8 -*-
"""Dark mode fixes: replace hardcoded white backgrounds with CSS vars"""
import io

# 1) global.css: white -> var(--color-surface)
p = r'C:\Users\nonam\smart-classroom-support\frontend\src\styles\global.css'
s = io.open(p, 'r', encoding='utf-8').read()
s2 = s.replace('  background: white;', '  background: var(--color-surface);')
io.open(p, 'w', encoding='utf-8', newline='').write(s2)
print('global.css white->surface:', s.count('  background: white;'), 'occurrences replaced')

# 2) App.tsx: chart tooltip '#FFFFFF' -> var(--color-surface)
p2 = r'C:\Users\nonam\smart-classroom-support\frontend\src\App.tsx'
s = io.open(p2, 'r', encoding='utf-8').read()
s2 = s.replace("background: '#FFFFFF', fontSize: 12,", "background: 'var(--color-surface)', fontSize: 12,")
io.open(p2, 'w', encoding='utf-8', newline='').write(s2)
print('App.tsx tooltip fixed:', s.count("background: '#FFFFFF', fontSize: 12,"))
