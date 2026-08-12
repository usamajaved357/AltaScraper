"""auth/ -- who someone is, and what they are allowed to do.

Two modules, deliberately separated:
  users.py -- the records: accounts, passwords, invitations, permissions
  guard.py -- the enforcement: which request needs which permission

Nothing else in the app decides whether an action is allowed. If a permission
question is being answered anywhere outside this package, that is a bug.
"""
