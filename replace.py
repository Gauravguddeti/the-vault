import os
import re

directory = r'd:\ClgStuff\The Vault\frontend\src'
replacements = [
    (r'linear-gradient\(135deg, #0f0f1a 0%, #1a0e2e 100%\)', 'var(--surface-0)'),
    (r'linear-gradient\(135deg, #4f46e5, #7c3aed\)', 'var(--accent)'),
    (r'linear-gradient\(135deg,#4f46e5,#7c3aed\)', 'var(--accent)'),
    (r'linear-gradient\(90deg, #4f46e5, #7c3aed\)', 'var(--accent)'),
    (r'linear-gradient\(135deg,rgba\(79,70,229,0\.2\),rgba\(124,58,237,0\.2\)\)', 'rgba(194,1,20,0.15)'),
    (r'radial-gradient\(ellipse 60% 40% at 50% 10%, rgba\(99,102,241,0\.18\), transparent\)', 'transparent'),
    (r'radial-gradient\(ellipse 70% 50% at 50% -20%, rgba\(99, 102, 241, 0\.15\), transparent\)', 'transparent'),
    (r'linear-gradient\(135deg,#818cf8,#c084fc\)', 'var(--accent)'),
    (r'boxShadow: "0 0 40px rgba\(99,102,241,0\.4\)"', 'boxShadow: "0 4px 0 #8a000e"'),
    (r'boxShadow: "0 0 16px rgba\(99,102,241,0\.4\)"', 'boxShadow: "0 4px 0 #8a000e"'),
    (r'boxShadow: "0 0 12px rgba\(99,102,241,0\.3\)"', 'boxShadow: "0 4px 0 #8a000e"')
]

for root, _, files in os.walk(directory):
    for file in files:
        if file.endswith('.tsx') or file.endswith('.ts'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content
            for old, new in replacements:
                new_content = re.sub(old, new, new_content)
                
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {filepath}")
