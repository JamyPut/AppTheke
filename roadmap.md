# AppTheke Roadmap

Ideas that are not part of the current step go here, not into the code.

Test for every new idea:
1. Does this improve the core experience?
2. Can it wait until after the MVP?
3. Will this make maintenance harder?

If the answer to the last two is yes, it goes on this list.

## Next up (after the MVP skeleton works)

1. **Automatic scanning** of install directories (e.g. Program Files) to find installed tools and suggest catalog entries.
   - Open questions: which folders, how often (startup / timer / button), how to match a folder to a tool.

## MVP checklist (portable Windows exe with GUI)

- [x] Database: tools, categories (one per tool), tags (many per tool)
- [x] Add tool
- [x] Search by name
- [ ] Edit tool
- [ ] Delete tool
- [ ] Tool detail page
- [ ] Download button (fetches setup/executable from the entered URL)
- [ ] Package with PyInstaller

## Phase 2

- Self-hosted web app (Flask + HTML/CSS/JS), reusing `core/`
- Decide then whether Eleventy has any role (static docs/landing page only)

## Later / ideas

- Multi-user support
- Code signing for the exe (avoids antivirus false positives)
