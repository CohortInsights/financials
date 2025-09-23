// Load userData JSON injected into dashboard.html

var userData = JSON.parse(document.getElementById("user-data").textContent);
var year_list = userData.years;
var start_year = year_list[0];

// Invoked upon page load to populate yearDropdown menu from year_list
function populateYearDropdown(yearDropdown) {
    yearDropdown.innerHTML = ''; // Clear existing options
    year_list.forEach(year => {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        yearDropdown.appendChild(option);
    });
}

function setStartYear() {
    const yearDropdown = document.getElementById('yearDropdown');
    let value = yearDropdown.value;
    if (value !== start_year) {
        start_year = value;
        console.log("Selected start year:", start_year);
    }
}

function reloadPage() {
    window.location.href = '/reload';
}

// Set up UI after page load
document.addEventListener('DOMContentLoaded', function() {
    const yearDropdown = document.getElementById('yearDropdown');
    populateYearDropdown(yearDropdown);
    yearDropdown.addEventListener('change', setStartYear);

    const reloadButton = document.getElementById('reloadButton');
    reloadButton.addEventListener('click', reloadPage);
});
