odoo.define('hrmis_user_profiles_updates.cadre_toggle', function (require) {
    'use strict';

    $(document).ready(function () {
        const cadreSelect = document.querySelector('.js-cadre-select');
        const otherField = document.querySelector('.js-cadre-other');

        if (!cadreSelect || !otherField) {
            return;
        }

        const input = otherField.querySelector('input');

        const toggleOther = () => {
            if (cadreSelect.value === 'other') {
                otherField.classList.remove('d-none');
                input.required = true;
            } else {
                otherField.classList.add('d-none');
                input.required = false;
                input.value = '';
            }
        };

        toggleOther();
        cadreSelect.addEventListener('change', toggleOther);
    });
});
