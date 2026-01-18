# Default Guardrails

## Code Quality

- Write clean, readable code with meaningful names
- Follow existing code style and patterns in the codebase
- Add comments only where logic isn't self-evident
- Keep functions focused and reasonably sized

## Safety

- Never introduce security vulnerabilities (injection, XSS, etc.)
- Validate inputs at system boundaries
- Handle errors gracefully
- Don't expose sensitive information in logs or errors

## Testing

- Test your changes before reporting success
- Consider edge cases and error conditions
- Verify existing functionality isn't broken

## Git

- Make atomic, focused commits
- Write clear commit messages
- Don't commit secrets, credentials, or sensitive data

## Communication

- Be clear about what you changed and why
- Report blockers or uncertainties promptly
- Ask for clarification when requirements are ambiguous
