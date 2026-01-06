/** @odoo-module **/
import publicWidget from 'web.public.widget';

publicWidget.registry.RemoveFooter = publicWidget.Widget.extend({
    selector: 'body',
    start: function () {
        const $footer = $('#bottom');
        if ($footer.length) {
            $footer.remove();
        }
    },
});
