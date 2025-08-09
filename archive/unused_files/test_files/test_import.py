import sys
print(sys.path)
try:
    import transkribator_modules
    print('Import OK')
except ImportError as e:
    print(f'Import Error: {e}') 