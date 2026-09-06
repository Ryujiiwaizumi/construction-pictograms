# Repository instructions

## Scope

These instructions apply to the entire repository. The user's explicit request takes precedence. For pictogram production specifications, also follow `docs/pictogram_guidelines.md`.

## Required workflow

- Start each task from the latest `main` and create a task-specific branch.
- Do not commit or push directly to `main`.
- Complete the requested changes, validate them, push the work branch, and create a pull request targeting `main`.
- Do not merge the pull request. Leave the final review and merge to the repository owner.
- Keep each pull request focused on the requested task only.

## Pictogram deliverables

- For every new or updated pictogram, maintain the SVG master, generate the matching PNG, and update `catalog/catalog.md`.
- Follow all visual, naming, size, and export requirements in `docs/pictogram_guidelines.md`.
- Do not add source or reference photographs, screenshots, or intermediate generated images to the repository.
- Remove or abstract identifying details from references, including faces, company logos, project names, addresses, site locations, and worker-specific details.

## Privacy and repository hygiene

- Before committing, inspect the staged diff for secrets, personal information, and local-machine information.
- Do not commit personal email addresses, phone numbers, private addresses, real company or construction-site details, credentials, tokens, secrets, usernames, or absolute local paths such as `C:\\Users\\...`.
- Do not commit temporary files, editor metadata, caches, build artifacts, or unrelated local files.

## Commit identity checks

- New commits must use a GitHub noreply address for both author and committer.
- Allowed addresses are `142085167+Ryujiiwaizumi@users.noreply.github.com` and `noreply@github.com`.
- Before pushing, verify every new commit in the branch. If any author or committer email is not allowed, rewrite the local commit before publishing.
- After creating the pull request, verify the commit identity on GitHub. If identity cannot be verified, stop and report the issue instead of merging.
