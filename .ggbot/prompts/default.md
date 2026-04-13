# Project-Specific Configuration
Custom prompt layer for this project.

## Project Context
This is the GGbot project itself - a CLI agent framework in Python. When working on this codebase:

### Codebase Structure
- Main entry point: `ggbot/cli.py`
- Core modules in `ggbot/core/`
- Tools in `ggbot/tools/`
- UI components in `ggbot/ui/`
- Tests in `tests/`

### Development Guidelines
1. **Testing**: Always run tests after making changes
2. **Type Safety**: Use type hints consistently
3. **Error Handling**: Graceful error handling with clear messages
4. **Documentation**: Keep docstrings and comments up to date

### Common Tasks
- Adding new tools: Follow the pattern in existing tool modules
- Modifying agent loop: Ensure transcript compatibility
- Updating prompts: Maintain backward compatibility

## Task-Specific Instructions
For common operations, follow these patterns:

### Bug Fixes
1. Reproduce the issue
2. Identify root cause
3. Make minimal fix
4. Add test case if applicable

### Feature Development
1. Understand requirements
2. Design implementation approach
3. Implement incrementally
4. Test thoroughly

### Code Review
1. Check for security issues
2. Verify adherence to project conventions
3. Ensure proper error handling
4. Confirm test coverage