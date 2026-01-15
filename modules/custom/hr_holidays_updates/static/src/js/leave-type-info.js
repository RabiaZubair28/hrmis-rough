/** @odoo-module **/

document.addEventListener("DOMContentLoaded", function () {
  const leaveTypeSelect = document.querySelector(".js-hrmis-leave-type");
  const leaveInfoDiv = document.querySelector(".js-leave-type-info");

  if (leaveTypeSelect && leaveInfoDiv) {
    leaveTypeSelect.addEventListener("change", function () {
      const selectedOption = this.options[this.selectedIndex];

      if (this.value) {
        // Get data attributes
        const balance = parseFloat(selectedOption.dataset.balance || 0);
        const maxYear = parseFloat(selectedOption.dataset.maxYear || 0);
        const maxRequest = parseFloat(selectedOption.dataset.maxRequest || 0);
        const maxMonth = parseFloat(selectedOption.dataset.maxMonth || 0);
        const maxTimes = parseInt(selectedOption.dataset.maxTimes || 0);
        const unpaid = selectedOption.dataset.unpaid === "1";

        // Show info panel
        leaveInfoDiv.style.display = "block";

        // Update balance
        leaveInfoDiv.querySelector(".js-balance-value").textContent =
          balance.toFixed(1);

        // Show/hide no balance warning
        const noBalanceDiv = leaveInfoDiv.querySelector(".js-leave-no-balance");
        const balanceDiv = leaveInfoDiv.querySelector(".js-leave-balance");

        if (balance <= 0) {
          noBalanceDiv.style.display = "block";
          balanceDiv.style.display = "none";
        } else {
          noBalanceDiv.style.display = "none";
          balanceDiv.style.display = "block";
        }

        // Show max duration
        const maxDiv = leaveInfoDiv.querySelector(".js-leave-max");
        const maxValueSpan = leaveInfoDiv.querySelector(".js-max-value");

        if (maxYear > 0) {
          maxDiv.style.display = "block";
          maxValueSpan.textContent = maxYear + " days/year";
        } else if (maxRequest > 0) {
          maxDiv.style.display = "block";
          maxValueSpan.textContent = maxRequest + " days/request";
        } else if (maxMonth > 0) {
          maxDiv.style.display = "block";
          maxValueSpan.textContent = maxMonth + " days/month";
        } else {
          maxDiv.style.display = "none";
        }

        // Show max times in service
        const timesDiv = leaveInfoDiv.querySelector(".js-leave-times");
        const timesValueSpan = leaveInfoDiv.querySelector(".js-times-value");

        if (maxTimes > 0) {
          timesDiv.style.display = "block";
          timesValueSpan.textContent = maxTimes;
        } else {
          timesDiv.style.display = "none";
        }

        // Show unpaid warning
        const unpaidDiv = leaveInfoDiv.querySelector(".js-leave-unpaid");
        unpaidDiv.style.display = unpaid ? "block" : "none";
      } else {
        leaveInfoDiv.style.display = "none";
      }
    });
  }
});
