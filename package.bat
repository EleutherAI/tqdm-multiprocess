del dist\* /Q
python setup.py sdist bdist_wheel
python -m twine upload --repository pypi dist/*