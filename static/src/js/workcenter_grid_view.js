var plan_id = 0;
var baseURI = window.location.href;
var hashtag_split = baseURI.split("#");
var str_contain_id = "";

if (hashtag_split[1].includes("id=")) {
    str_contain_id = hashtag_split[1];
} else {
    for (let i = 0; i < hashtag_split.length; i++) {
        if (hashtag_split[i].includes("id=")) {
            str_contain_id = hashtag_split[i];
        }
    }
}

var ampersand_split = str_contain_id.split("&");
for (let i = 0; i < ampersand_split.length; i++) {
    if (ampersand_split[i].includes("id=")) {
        if (ampersand_split[i].split("=")[0] === "id") {
            plan_id = parseInt(ampersand_split[i].split("=")[1]);
        }
    }
}
if (isNaN(plan_id)) {
    plan_id = 0;
} 
var url = "api/mrp_workingtime_workcenter/plan_order/" + plan_id;

$.ajax({
    async: true,
    type: "GET",
    url: url,
    dataType: "json",
    success: function(data) {
        new gridjs.Grid({
            columns: [
                {name: "ID", hidden: true},
                "Work Center",
                "Department",
                "Duration (hours)"
            ],
            sort: true,
            search: true,
            resizable: true,
            pagination: {limit: 20},
            fixedHeader: true,
            data: data,
        }).render(document.getElementById("erpvn_planning_management.workcenter_table_view"));
    },

    error: function(xhr, ajaxOptions, thrownError) {
        alert('Error from sever, Contact Odoo Coder !');
    }
});