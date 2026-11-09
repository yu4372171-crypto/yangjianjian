## What changed

Describe the user-visible problem and the resulting behavior.

## Validation

- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m compileall -q backend tests`
- [ ] `dotnet build apps/desktop/YangJianJian.Desktop.csproj -c Release`
- [ ] Tested the affected workflow with synthetic media

## Safety

- [ ] No customer media, projects, logs, model weights, binaries or credentials
- [ ] Downloads and update packages use HTTPS, size and SHA-256 validation
- [ ] Deletion or overwrite paths require a confirmed target and remain bounded
