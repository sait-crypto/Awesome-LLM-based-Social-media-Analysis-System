from src.convert import ReadmeGenerator
rg = ReadmeGenerator()
print('--- Quick Links ---')
print(rg._generate_quick_links())
print('--- Tables (prefix) ---')
print(rg.generate_readme_tables()[:800])
