from . import models
from . import controllers


def _drop_leave_approver_user_fk(cr):
    """
    Drop FK constraint `hr_leave_approver_user_rel_user_id_fkey` if it exists.

    This constraint can block leave approvals in deployments where some custom
    code path mistakenly attempts to delete users or otherwise trips the FK.
    """
    cr.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'hr_leave_approver_user_rel_user_id_fkey'
            ) THEN
                ALTER TABLE hr_leave_approver_user_rel
                    DROP CONSTRAINT hr_leave_approver_user_rel_user_id_fkey;
            END IF;
        END $$;
        """
    )


def post_init_hook(env):
    """
    Odoo calls post-init hooks with a single argument: `env`.
    """
    _drop_leave_approver_user_fk(env.cr)


def uninstall_hook(env):
    # Nothing to restore (dropping FK is intentional).
    return