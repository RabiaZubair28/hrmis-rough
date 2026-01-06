odoo.define('custom_login.password_validation', function (require) {
    "use strict";

    function initPasswordValidation() {
        const newPassword = document.getElementById('new_password');
        const confirmPassword = document.getElementById('confirm_password');
        const matchMsg = document.getElementById('passwordMatchMsg');
        const form = document.getElementById('passwordForm');

        if (!newPassword || !confirmPassword || !matchMsg || !form) {
            return;
        }

        const passwordPattern = /^(?=.*\d)(?=.*[a-z])(?=.*[A-Z]).{8,}$/;

        function validateMatch() {
            if (!confirmPassword.value) {
                matchMsg.textContent = "";
                matchMsg.className = "small";
                return;
            }

            if (confirmPassword.value !== newPassword.value) {
                matchMsg.textContent = "Doesn't match the new password";
                matchMsg.className = "text-danger small";
            } else {
                matchMsg.textContent = "Passwords match";
                matchMsg.className = "text-success small";
            }
        }

        // 🔥 Real-time typing feedback
        newPassword.addEventListener('input', validateMatch);
        confirmPassword.addEventListener('input', validateMatch);

        // 🚫 Final submit guard
        form.addEventListener('submit', function (e) {
            if (!passwordPattern.test(newPassword.value)) {
                e.preventDefault();
                matchMsg.textContent =
                    "Password must be 8+ chars with uppercase, lowercase and a number.";
                matchMsg.className = "text-danger small";
                newPassword.focus();
                return;
            }

            if (newPassword.value !== confirmPassword.value) {
                e.preventDefault();
                matchMsg.textContent = "Passwords do not match";
                matchMsg.className = "text-danger small";
                confirmPassword.focus();
            }
        });
    }

    // ⏳ Odoo-safe DOM hook
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPasswordValidation);
    } else {
        initPasswordValidation();
    }
});
