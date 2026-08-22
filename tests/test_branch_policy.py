from __future__ import annotations

import pytest
from scripts.validate_branch_name import BranchNameError, validate_branch_name


def test_branch_matching_repository_account_is_allowed() -> None:
    branch = "cloga/social-publish-core"
    assert validate_branch_name(branch) == branch


def test_corporate_identity_branch_is_rejected() -> None:
    with pytest.raises(BranchNameError, match="prohibited identity"):
        validate_branch_name("lochen-microsoft-social-publish-core")


def test_unscoped_branch_is_rejected() -> None:
    with pytest.raises(BranchNameError, match="active GitHub account"):
        validate_branch_name("social-publish-core")


def test_other_personal_account_prefix_is_rejected() -> None:
    with pytest.raises(BranchNameError, match="cloga/"):
        validate_branch_name("lochen/social-publish-core")
