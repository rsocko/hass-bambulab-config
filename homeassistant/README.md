# Home Assistant Deployable Root

This directory is intended to sync directly to Home Assistant `/config`.

- `packages/3d_printing` -> `/config/packages/3d_printing`
- `www/3d_printing/` -> `/config/www/3d_printing/`

For 3D printing features, package content is organized under:

- `packages/3d_printing/<feature>/<domain>/...`

If there are files that relate to a package that are non-yaml (images, etc.) they are deployed under the www portion of the /config directory. The same naming convention then follows the packages format and structure. The package name should match.

See the detailed [[DEPLOYMENT_STRUCTURE]] guidance.

## Required `configuration.yaml` wiring

Configure Home Assistant to load package feature loaders from an include file inside `packages/3d_printing`:

```yaml
homeassistant:
	packages: !include packages/3d_printing/_feature_loaders.yaml
```

Example include file (`/config/packages/3d_printing/_feature_loaders.yaml`):

```yaml
core_loader: !include packages/3d_printing/core/core_loader.yaml
```

Path note: `!include` and `!include_dir_merge_list` paths are resolved from the Home Assistant config root (`/config`), so references like `packages/3d_printing/core/sensors` are correct.

*Note: currently the deployment doesn't allow for www-only files to be deployed. The deployment actions assume everything is package based and optionally includes www related files.*
