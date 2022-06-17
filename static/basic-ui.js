var current_devices = []
var masterList = ["com.DefaultCompany.Kindred", "com.IndigoStorm.TheMuseumofImaginedFutures", "com.NoGhost.OffTheRecord", "com.SV.LifeCycles", "com.Shroomstudio.Promenade", "com.Visualise.GetPunked", "com.epicgames.Storyfutures"]
var status_global = document.getElementById("status");
var statusToast = new bootstrap.Toast(document.getElementById('statusToast'));
class DeviceTable extends HTMLElement {
    constructor(deviceList) {
        super();
        this.deviceList = deviceList;
        this.attachShadow({ mode: 'open' });
        var bootstrapStyles = document.createElement('link')
        bootstrapStyles.rel = 'stylesheet'
        bootstrapStyles.href = 'static/bootstrap-5.2.0-beta1-dist/css/bootstrap.css'
        this.shadowRoot.appendChild(bootstrapStyles);
        this.tableGenerator(deviceList);
        this.classList.add("w-100");
        this.classList.add("p-0");


    }
    connectedCallback() {
    }
    tableGenerator(deviceList) {
        this.shadowRoot.appendChild(document.querySelector("#devices-table-template").content.cloneNode(true));
        var tableBody = this.shadowRoot.querySelector("#body-container");
        deviceList.forEach(device => {
            tableBody.appendChild(this.itemGenerator(device));
            this.getBatteryPercentage(device.id);
            this.getCurrentExperience(device.id);
        });
    }
    itemGenerator(device) {
        let row = document.querySelector("#device-list-item").content.cloneNode(true)
        row.querySelector("tr").setAttribute("id", device.id)
        if (device.icon) {
            row.querySelector("tr").setAttribute("name", device.icon.text)
        }
        else {
            row.querySelector("tr").setAttribute("name", device.id)
        }

        if (device.icon) {

            var col = device.icon.col
            var icon = device.icon.icon


            $('.icon-set').each(function () {
                if ($(this).data('col') === col && $(this).data('icon') === icon) {
                    var found = $(this).parent().find('svg')
                    var cloned_icon = $(found).clone();
                    cloned_icon.css('color', col);

                    row.querySelector("#setIcon").innerHTML = cloned_icon[0].outerHTML;

                }
            });
        }
        if (device.ip === false) {

            row.querySelector("#deviceConnection").innerHTML = "Wired"
            row.querySelector("#deviceConnection").classList.remove("text-success")
            row.querySelector("#deviceConnection").classList.add("text-warning")
        }
        this.checkLoadedExperiences(device.id);
        return row;
    }
    getBatteryPercentage(id) {

        fetch("/battery/" + id).then(response => {
            return response.json()
        }).then(data => {
            if (data >= 60) {
                this.shadowRoot.getElementById(id).querySelector("#batteryBadge").classList.add("text-bg-success")
                this.shadowRoot.getElementById(id).querySelector("#batteryBadge").classList.remove("text-bg-danger")
                this.shadowRoot.getElementById(id).querySelector("#batteryBadge").classList.remove("text-bg-warning")
            } else if (data < 60 && data >= 30) {
                this.shadowRoot.getElementById(id).querySelector("#batteryBadge").classList.add("text-bg-warning")
                this.shadowRoot.getElementById(id).querySelector("#batteryBadge").classList.remove("text-bg-success")
                this.shadowRoot.getElementById(id).querySelector("#batteryBadge").classList.remove("text-bg-danger")
            } else {
                this.shadowRoot.getElementById(id).querySelector("#batteryBadge").classList.add("text-bg-danger")
                this.shadowRoot.getElementById(id).querySelector("#batteryBadge").classList.remove("text-bg-success")
                this.shadowRoot.getElementById(id).querySelector("#batteryBadge").classList.remove("text-bg-warning")

            }
            this.shadowRoot.getElementById(id).querySelector("#batteryPercent").innerHTML = data + "%";

        })
    }
    getCurrentExperience(id) {
        fetch("/current-experience/" + id).then(response => {
            return response.json()
        }).then(data => {
            this.shadowRoot.getElementById(id).querySelector("#deviceCurrentExperience").innerHTML = data.current_app;

        })
    }
    checkLoadedExperiences(id) {
        fetch("/loaded-experiences/" + id).then(response => {
            return response.json()
        }).then(data => {
            //this.shadowRoot.getElementById(id).querySelector("#deviceLoadedExperiences").innerHTML = data.length;
            let package_list = []
            data.forEach(experience => {
                let expid = experience.package
                package_list.push(expid)
            })
            let includesall = masterList.every(element => package_list.indexOf(element) > -1);
            if (includesall) {
                this.shadowRoot.getElementById(id).querySelector("#deviceExperiencesStatus").classList.add("text-success")
                this.shadowRoot.getElementById(id).querySelector("#deviceExperiencesStatus").classList.remove("text-danger")
                this.shadowRoot.getElementById(id).querySelector("#deviceExperiencesStatus").innerHTML = "Loaded"
            } else {
                this.shadowRoot.getElementById(id).querySelector("#deviceExperiencesStatus").innerHTML = "Not Loaded"
                this.shadowRoot.getElementById(id).querySelector("#deviceExperiencesStatus").classList.add("text-danger")
                this.shadowRoot.getElementById(id).querySelector("#deviceExperiencesStatus").classList.remove("text-success")
            }

        })
    }
    updateStatus(list) {
        list.forEach(device => {
            this.getCurrentExperience(device.id);
            this.getBatteryPercentage(device.id);

        })
    }
    getSelected() {
        let selected = []
        this.shadowRoot.querySelector("#body-container").querySelectorAll("input").forEach(check => {
            if (check.checked) {
                selected.push(check.parentElement.parentElement.id)
            }
        })
        return selected
    }
    selectAll() {
        this.shadowRoot.querySelector("#body-container").querySelectorAll("input").forEach(check => {
            check.checked = true
        })
    }
    deselectAll() {
        this.shadowRoot.querySelector("#body-container").querySelectorAll("input").forEach(check => {
            check.checked = false
        })
    }
    overrideSelected() {
        if (this.shadowRoot.querySelector("#selectControl").checked === true) {
            this.selectAll()
        }
        else {
            this.deselectAll()
        }
    }
    updateSelected(el) {

        if (el.checked === false) {
            this.shadowRoot.querySelector("#selectControl").checked = false
        }
    }
}
customElements.define('device-table', DeviceTable);


function get_devices() {
    console.log('Polling for new devices')
    fetch('devices', {
        method: 'GET',
    })
        .then(function (response) {
            if (!response.ok) {
                throw Error(response.statusText);
            }
            return response.json()
        })
        .then(function (json) {
            var devices_count = json['devices'].length;


            if (JSON.stringify(json['devices']) != JSON.stringify(current_devices)) {
                console.log('Found changes')
                document.getElementById("main-container").innerHTML = "";
                var devicetable = new DeviceTable(json['devices'])
                document.getElementById("main-container").appendChild(devicetable);

                current_devices = json['devices'];
                devicetable.updateStatus(devicetable.deviceList);
            }
            document.querySelector("device-table").updateStatus(document.querySelector("device-table").deviceList);
            if (devices_count === 0) {
                document.getElementById("main-container").innerHTML = `<h2 class="w-100 text-center p-3" id="no-devices">No Devices Connected.</h2>`

            }

        })
        .catch(function (error) {
            console.log(error);
        })

}
function set_icon(el) {
    var icon_modal = $('#setIconModal');
    var device_id = el.getAttribute('id');
    var el_name = el.getAttribute('name');
    $('#setIconModalLabel').val(el_name);
    $(icon_modal).modal('show');

    function icon_modal_helper() {
        // put your default event here
        $(icon_modal).modal('hide');
        var selected = $("input[type='radio'][name='icon-options']:checked");
        if (selected) {
            var col = $(selected[0]).data('col');
            var icon = $(selected[0]).data('icon');
            var cloned_icon = $(selected.parent().find('svg')[0]).clone();
            cloned_icon.css('color', col);
            var el_text = $('#setIconModalLabel').val();
            if (el_text.length < 3) el_text += 'name too short'

            fetch('set-device-icon/' + device_id, {
                method: 'POST',
                body: JSON.stringify({ 'col': col, 'icon': icon, 'text': el_text }),
                headers: { "Content-type": "application/json" }
            }).then(function (response) {
                if (!response.ok) {
                    throw Error(response.statusText);
                }
                return response.json();
            }).then((response) => {

            }).catch(function (error) {

            }).finally(function () {
                $('.icon-set').off("click", icon_modal_helper);
                location.reload();
            })
        }
    }

    $('.icon-set').on("click", icon_modal_helper);
}

function startExperience() {

    var devices = document.querySelector("device-table").getSelected();

    var body = { "devices": devices, "experience": document.getElementById("set_choices_dropdown").value }
    send({
        body: body,
        start: function () {
            document.getElementById("startButton").classList.add("disabled");
        },
        url: '/start',
        success: function (data) {
            showStatus("Experience has started on " + data["device_count"] + " devices!");


        },
        problem: function (error) {
            showStatus("Error starting experience: " + error);
        },
        finally: function () {
            $('#setExperienceModal').modal('hide')
            document.getElementById("startButton").classList.remove("disabled");
        }
    })


}
function send(params) {
    var selected_devices = document.querySelector("device-table").getSelected();



    if (!params['headers']) params['headers'] = {};
    if (!params['headers']["Content-type"]) params['headers']["Content-type"] = "application/json";
    if (!params['method']) params['method'] = 'POST';

    if (!params['body']) {
        if (params['method'].toLowerCase() === 'post') {
            params['body'] = {}
        }
    }
    if (!params['body']['devices']) {
        params['body']['devices'] = selected_devices;
    }

    if (params['start']) params['start']();

    fetch(params['url'], {
        method: params['method'],
        body: JSON.stringify(params['body']),
        headers: params['headers']
    }).then(function (response) {
        if (!response.ok) {
            throw Error(response.statusText);
        }
        return response.json();
    }).then((response) => {
        if (response['success'] === false) {
            throw Error(response['error']);
        }
        if (params['success']) params['success'](response);
    }).catch(function (error) {
        if (params['problem']) params['problem'](error);
        showStatus(error, true);

    }).finally(function () {
        if (params['finally']) params['finally']();
    });
}
var showStatus = (text = "The showStatus function was used incorrectly and status text was not defined", isError = false) => {
    if (isError === true) {
        document.getElementById("statusToast").classList.add("bg-danger");
        document.getElementById("toastClose").classList.add("btn-close-white");
        status_global.classList.add("text-white");
    } else if (document.getElementById("statusToast").classList.contains("bg-danger")) {
        document.getElementById("statusToast").classList.remove("bg-danger");
        document.getElementById("toastClose").classList.remove("btn-close-white");
        status_global.classList.remove("text-white");
    }
    status_global.innerHTML = text;
    statusToast.show();
}
get_devices();
setInterval(get_devices, 8000);
