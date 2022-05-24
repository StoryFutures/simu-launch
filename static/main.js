//GLOBAL VARS
var status_global = document.getElementById("status");
var statusToast = new bootstrap.Toast(document.getElementById('statusToast'));
var cardList = []

//HELPER FUNCTIONS
function transformFormData() {
    var myForm = document.getElementById('myForm');
    var qs = new URLSearchParams(new FormData(myForm)).toString();
    myForm.action = 'http://127.0.0.1:8000/submit?' + qs;
}

// doing via object for reasons of clarity
// params = {
//  url: '',
//  method: default POST
//  body: '',
//  success: '',
//  problem: '',
//  start: '',
//  finally: '',
// }

function add_devices(obj) {

    console.log(obj)
}

function send(params) {
    if (!params['headers']) params['headers'] = {};
    if (!params['headers']["Content-type"]) params['headers']["Content-type"] = "application/json";
    if (!params['method']) params['method'] = 'POST';

    console.log(params['body'])

    if (!params['body']) {
        if (params['method'].toLowerCase() === 'post') {
            params['body'] = {}
        }
    }
    if (!params['body']['devices']) {
        params['body']['devices'] = devices_manager.devices();
    }

    if (params['start']) params['start']();

    console.log(params)

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

var showStatus = (text = "The showStatus function was used incoorrectly and status text was not defined", isError = false) => {
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

function uploadAPKForm() {
    const formElement = document.getElementById('uploadForm')
    var formData = new FormData(formElement)

    fetch('/upload', {
        method: 'POST',
        body: formData
    }).then(function (response) {
        if (!response.ok) {
            throw Error(response.statusText);
        }

        $('#uploadModal').modal('hide')

        return response.json();
    }).then(function (data) {
        showStatus("Experience has been uploaded. You may now load it on devices");
    }).catch(function (error) {
        console.log(error);
        showStatus("Error uploading experience to server: " + error);
    })
}

function remove_class(element) {
    var lastClass = element.attr('class').split(' ').pop();
    if (lastClass.includes("alert-")) {
        element.removeClass(lastClass)
    }
}

//BUTTON EVENTS
function startExperience() {

    var devices = []
    selectedCards().forEach(element => {
        devices.push(element.deviceId)
    });
    var body = {"devices": devices, "experience": document.getElementById("set_choices_dropdown").value}
    send({
        body: body,
        start: function () {
            document.getElementById("startButton").classList.add("disabled");
        },
        url: '/start',
        success: function (data) {
            showStatus("Experience has started on " + data["device_count"] + " devices!");
            ;

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

function loadExperience() {


    var devices = []
    selectedCards().forEach(element => {
        devices.push(element.deviceId)
    });
    var body = {"devices": devices, "experience": document.getElementById("load_choices_dropdown").value}
    send({
        url: '/load',
        start: function () {
            document.getElementById("loadButton").classList.add("disabled");
        },
        body: body,
        success: function (data) {
            $('#loadModal').modal('hide');
            showStatus("Experience has loaded on " + data["device_count"] + " devices!");
        },
        problem: function (error) {
            showStatus("Error loading experience: " + error);

        },
        finally: function () {
            document.getElementById("loadButton").classList.remove("disabled");
        }
    })
}


function addRemoteExperience() {

    const formElement = document.getElementById('addExperienceForm')
    var formData = new FormData(formElement)

    send({
        url: '/add-remote-experience',
        start: function () {

        },
        body: {
            "apk_name": document.getElementById("apk_name").value,
            "command": document.getElementById("command").value,
        },
        success: function () {
            $('#addExperienceModal').modal('hide');
            showStatus("Experience has been added! You may now set it as the active experience");
        },
        finally: function () {

        }
    })

}

function removeRemoteExperience() {

    const formElement = document.getElementById('removeExperienceForm')
    var formData = new FormData(formElement)

    send({
        url: '/remove-remote-experience',
        start: function () {
            document.getElementById("removeRemoteButton").classList.add("disabled");
        },
        body: formData,
        success: function () {
            $('#removeExperienceModal').modal('hide');
            showStatus("Experience has been removed!");
        },
        finally: function () {
            document.getElementById("removeRemoteButton").classList.remove("disabled");
        }
    })

}


function stopExperience() {
    var devices = []
    selectedCards().forEach(element => {
        devices.push(element.deviceId)
    });
    var body = {"devices": devices, "experience": document.getElementById("stop_choices_dropdown").value}
    if (document.getElementById("stop_choices_dropdown").value === "current") {
        selectedCards().forEach(device => {
            stop_some_experience(device.shadowRoot.getElementById('checkExperiences'))
        })
    } else {
        send({
            url: '/stop',
            start: function () {
                document.getElementById("stopButton").classList.add("disabled");
            },
            body: body,
            success: function () {

                showStatus("Experience has stopped on device(s)!");
            },
            finally: function () {
                $('#stopExperienceModal').modal('hide');
                document.getElementById("stopButton").classList.remove("disabled");
            }
        })
    }
}

function connectDevice() {


    send({
        url: '/connect',
        start: function () {
            document.getElementById("connectButton").classList.add("disabled");
        },

        success: function (data) {
            showStatus("Device connected with serial ID: " + data["serial"]);
            setTimeout(function () {
                location.reload();
            }, 3000);
        },
        problem: function (error) {
            showStatus("Error connecting device: " + error, true);
        },
        finally: function () {
            document.getElementById("connectButton").classList.remove("disabled");
        }
    })
}

function disconnectDevice() {

    var formData = new FormData()
    var devices = []
    selectedCards().forEach(element => {
        devices.push(element.deviceId)

    });
    formData.append("devices", devices)
    send({
        url: '/disconnect',


        start: function () {
            document.getElementById("disconnectButton").classList.add("disabled");
        },
        body: formData,
        success: function () {
            showStatus("All devices have been disconnected");
            setTimeout(function () {
                location.reload();
            }, 3000);
        },
        problem: function (error) {
            showStatus("Error disconnecting devices: " + error);
        },
        finally: function () {
            document.getElementById("disconnectButton").classList.remove("disabled");
        }
    })
}

function stopServer() {

    send({
        url: '/exit-server',
        start: function () {
            document.getElementById("stopServerButton").classList.add("disabled");
        },
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        },
        success: function () {
            showStatus("ADB server has stopped!");
        },
        problem: function (error) {
            showStatus("Error stopping server: " + error);
        },
        finally: function () {
            document.getElementById("stopServerButton").classList.remove("disabled");
        }
    })
}

function getScreenshots() {

    send({
        url: '/screen-grab',
        start: function () {
            document.getElementById("screenshotButton").classList.add("disabled");
        },
        method: 'GET',
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        },
        success: function () {
            showStatus("Screenshots have taken!");
            document.getElementById("screenshotButton").classList.remove("disabled");
        },
        problem: function (error) {
            showStatus("Error taking screenshots: " + error);
        },
        finally: function () {
            document.getElementById("screenshotButton").classList.remove("disabled");
        }
    })
}

//DEVICE CARDS
class DeviceCard extends HTMLElement {
    constructor(image, device, selected) {
        super();
        this.attachShadow({mode: 'open'});
        var bootstrapStyles = document.createElement('link')
        bootstrapStyles.rel = 'stylesheet'
        bootstrapStyles.href = 'static/bootstrap-5.2.0-beta1-dist/css/bootstrap.css'
        this.shadowRoot.appendChild(bootstrapStyles);
        this.shadowRoot.appendChild(document.querySelector("#device-card").content.cloneNode(true));
        this.image = image;
        this.deviceId = device['id'];
        this.device_icon = device['icon'];
        this.selected = selected;
        var checkbox = this.shadowRoot.getElementById("cardSelect");
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) {
                this.updateSelected(true)
            } else {
                this.updateSelected(false)
            }
        })

        if (this.device_icon) {
            var el = this.shadowRoot.getElementById('setIcon');
            $(el).children('svg').remove();

            var col = this.device_icon['col'];
            var icon = this.device_icon['icon'];
            var my_id = '#' + col + '-' + icon;

            $('.icon-set').each(function () {
                if ($(this).data('col') === col && $(this).data('icon') === icon) {
                    var found = $(this).parent().find('svg')
                    var cloned_icon = $(found).clone();
                    cloned_icon.css('color', col);
                    $(el).append(cloned_icon);
                }
            });
        }

        // setting this attribute on the nodes themselves to avoid future breakage during UI redesign
        for (var el_id of ['checkExperiences', 'stop_some_experience', 'setIcon']) {
            var el = this.shadowRoot.getElementById(el_id);
            // should really be setting data-device_id
            el.setAttribute('device_id', this.deviceId)
        }

        var check_battery_mins_wait = 5;
        this.getBatteryPercentage()
        setInterval(() => {
            this.getBatteryPercentage()
        }, check_battery_mins_wait * 60 * 1000);

    }

    updateSelected(selected) {
        if (selected === true) {
            this.selected = true;
            this.shadowRoot.getElementById("main-card").children[0].classList.add("shadow");
            checkSelected();
        } else {
            this.selected = false;
            this.shadowRoot.getElementById("main-card").children[0].classList.remove("shadow");
            checkSelected();
        }
    }

    getBatteryPercentage() {
        let result
        fetch("/battery/" + this.deviceId).then(response => {
            return response.json()
        }).then(data => {
            if (data >= 60) {
                this.shadowRoot.getElementById("batteryBadge").classList.add("text-bg-success")
                this.shadowRoot.getElementById("batteryBadge").classList.remove("text-bg-danger")
                this.shadowRoot.getElementById("batteryBadge").classList.remove("text-bg-warning")
            } else if (data < 60 && data >= 30) {
                this.shadowRoot.getElementById("batteryBadge").classList.add("text-bg-warning")
                this.shadowRoot.getElementById("batteryBadge").classList.remove("text-bg-success")
                this.shadowRoot.getElementById("batteryBadge").classList.remove("text-bg-danger")
            } else {
                this.shadowRoot.getElementById("batteryBadge").classList.add("text-bg-danger")
                this.shadowRoot.getElementById("batteryBadge").classList.remove("text-bg-success")
                this.shadowRoot.getElementById("batteryBadge").classList.remove("text-bg-warning")

            }
            this.shadowRoot.getElementById("batteryPercent").innerHTML = data + "%";
        })
    }

    updateImage(image) {
        this.image = image;
        this.shadowRoot.querySelector("img").src = image;
    }

    updateImage64(image64) {

        this.shadowRoot.querySelector("img").src = "data:image/png;base64, " + image64;
    }

    connectedCallback() {
        this.shadowRoot.querySelector("img").src = this.image;
        this.shadowRoot.querySelector("#device-name").innerHTML = this.deviceId;

    }
}

var deselectAll = function () {
    selectedCards().forEach(function (card) {
        card.updateSelected(false);
        card.shadowRoot.querySelector("input").checked = false
    })
}
var selectAll = function () {
    cardList.forEach(function (card) {
        card.updateSelected(true);
        card.shadowRoot.querySelector("input").checked = true
    })
}
window.customElements.define('device-card', DeviceCard);

testingarr = ["42345325", "654645", "65476", "746535", "23432432", "12315465"]

var devices_manager = function () {
    var api = {};

    var card_map = {}; // {device_name: {'card': my_card, 'poll': my_poll}

    var image_height = defaults.screen_height;
    var rate = defaults.screen_updates * 1000;

    api.refresh_devices = function () {
        location.reload();
    }

    function screengrab_polling(device, on) {
        if (!on) on = true;

        // let's always remove existing polling
        if (card_map[device]['poll']) {
            clearTimeout(card_map[device]['poll']);
            card_map[device]['poll'] = undefined;
        }

        if (on) {
            setTimeout(function () {
                poll();
                card_map[device]['poll'] = setTimeout(poll, rate);
            }, Math.random() * 1000);

        }

        var lock = false;

        function poll() {
            if (lock) {
                return
            }
            lock = true
            fetch("device-screen/" + rate + "/" + image_height + "/" + device)
                .then(function (response) {
                    return response.json()
                })
                .then(function (json) {
                    var b64_image = json['base64_image'];
                    card_map[device].updateImage64(b64_image);
                })
                .catch(function () {
                    console.log('error with polling for device ' + device)
                    api.refresh_devices()
                })
                .finally(function () {
                    card_map[device]['poll'] = setTimeout(poll, rate);
                    lock = false;
                })
        }
    }

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
            if (devices_count > 0) {
                document.getElementById('no-devices').remove();
            }

            for (var device of json['devices']) {
                var card = new DeviceCard("/static/images/placeholder.jpg", device, false);
                card.classList.add('col')
                cardList.push(card);
                var device_id = device['id'];

                document.querySelector("#main-container").prepend(card);
                card_map[device_id] = card
                screengrab_polling(device_id, true);
            }
        })
        .catch(function (error) {
            console.log(error);
        })


    api.devices = function () {
        return card_map.keys;
    }

    return api;
}();

var checkSelected = () => {
    if (selectedCards().length !== 0) {
        document.getElementById("navContainer").innerHTML = "";
        let navbarSelect = document.querySelector("#navbarSelect").content.cloneNode(true)
        document.getElementById("navContainer").appendChild(navbarSelect);
    } else {
        document.getElementById("navContainer").innerHTML = "";
        let navbar = document.querySelector("#navbarStandard").content.cloneNode(true)
        document.getElementById("navContainer").appendChild(navbar);
    }
}

var selectedCards = () => {
    var count = [];
    cardList.forEach((card) => {
        if (card.selected) {
            count.push(card);
        }
    })
    return count;
}

//VOLUME CONTROL
window.addEventListener('load', function () {

    var slider = $('#volume');


    slider.on('input', function () {
        var volume = parseInt(slider.val());
        $('.volume-label').text(volume);
    })

    slider.on('change', function (ev) {
        var volume = parseInt(slider.val());

        send({
            url: 'volume',
            body: {'volume': volume},
            success: function () {
                showStatus('Changed volume to ' + volume);
            },
            problem: function () {
                showStatus('Could not change volume to ' + volume, true);
            },
            finally: '',
        });

    });

})

var selectAllToggle = () => {
    if (selectedCards().length === cardList.length) {
        deselectAll();
    } else {
        selectAll();
    }
}

function gather_experiences(el) {
    var device_id = el.getAttribute('device_id');
    fetch('device-experiences/' + device_id, {
        method: 'GET',
    })
        .then(function (response) {
            if (!response.ok) {
                throw Error(response.statusText);
            }
            return response.text()
        })
        .then(function (html) {
            $('#experiences_modal_content').html(html);
            $('#experiencesModal').modal('show');
        })
        .catch(function (error) {
            console.log(error);
        })
}

function set_icon(el) {
    var icon_modal = $('#setIconModal');
    var device_id = el.getAttribute('device_id');
    $(icon_modal).modal('show');

    $('.icon-set').on("click", function () {
        // put your default event here
        $(icon_modal).modal('hide');
        var selected = $("input[type='radio'][name='icon-options']:checked");
        if (selected) {
            var col = $(selected[0]).data('col');
            var icon = $(selected[0]).data('icon');
            $(el).children('svg').remove();
            var cloned_icon = $(selected.parent().find('svg')[0]).clone();
            cloned_icon.css('color', col);
            $(el).append(cloned_icon);

            fetch('set-device-icon/' + device_id, {
                method: 'POST',
                body: JSON.stringify({'col': col, 'icon': icon}),
                headers: {"Content-type": "application/json"}
            }).then(function (response) {
                if (!response.ok) {
                    throw Error(response.statusText);
                }
                return response.json();
            }).then((response) => {

            }).catch(function (error) {


            })
        }
    });
}

function stop_some_experience(el) {

    var device = el.getAttribute('device_id');

    send({
        body: {'experience': '?'},
        start: function () {
        },
        url: '/command/stop-some-experience/' + device,
        success: function (data) {
            showStatus(data['outcome']);

        },
        problem: function (error) {
            showStatus("Error stopping experience: " + error);
        },
        finally: function () {

        }
    })
}


var ws = new WebSocket("ws://" + location.host + "/ws");
ws.onmessage = function (event) {

};

function sendMessage() {
    ws.send('hi')
}
