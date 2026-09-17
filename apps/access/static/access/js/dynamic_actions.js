/**
 * Dynamically filter Action dropdown based on selected Feature in FeatureGrantForm.
 */
document.addEventListener("DOMContentLoaded", function () {
    const featureSelect = document.getElementById("id_feature");
    const actionSelect = document.getElementById("id_action");

    if (!featureSelect || !actionSelect) {
        return;
    }

    function updateActionOptions() {
        const selectedFeatureId = featureSelect.value;
        const currentActionVal = actionSelect.value;
        let isCurrentActionStillValid = false;

        for (let i = 0; i < actionSelect.options.length; i++) {
            const opt = actionSelect.options[i];
            if (!opt.value) {
                // Empty option ("— Semua Action (Akses Penuh Fitur) —") is always available
                opt.hidden = false;
                opt.disabled = false;
                continue;
            }

            const actionFeatureId = opt.getAttribute("data-feature");
            if (!selectedFeatureId || actionFeatureId === selectedFeatureId) {
                opt.hidden = false;
                opt.disabled = false;
                if (opt.value === currentActionVal) {
                    isCurrentActionStillValid = true;
                }
            } else {
                opt.hidden = true;
                opt.disabled = true;
            }
        }

        // Reset to default empty option if the previously selected action doesn't belong to the new feature
        if (currentActionVal && !isCurrentActionStillValid) {
            actionSelect.value = "";
        }
    }

    featureSelect.addEventListener("change", updateActionOptions);
    // Initial run on page load (e.g. edit mode or validation error reload)
    updateActionOptions();
});
