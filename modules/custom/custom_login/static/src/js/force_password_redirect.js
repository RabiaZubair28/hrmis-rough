/** @odoo-module **/

import { registry } from "@web/core/registry";

const { Component } = owl;

class ForcePasswordRedirect extends Component {
    mounted() {
        window.location.href = "/force_password_reset";
    }
}

registry.category("actions").add("force_password_redirect", ForcePasswordRedirect);
