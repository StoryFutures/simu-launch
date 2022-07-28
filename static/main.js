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
    var selected_devices = [];
    if(params['devices']){
        selected_devices = params['devices']
    }
    else {
        selectedCards().forEach(element => {
            selected_devices.push(element.deviceId)
        });
    }

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
    var body = { "devices": devices, "experience": document.getElementById("set_choices_dropdown").value }
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
    var body = { "devices": devices, "experience": document.getElementById("load_choices_dropdown").value }
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
            "experience_name": document.getElementById("experience_name").value,
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
        },
        body: {
            "devices": [],
            "experience": document.getElementById("remove_choices_dropdown").value,
        },
        success: function () {
            $('#removeExperienceModal').modal('hide');
            showStatus("Experience has been removed!");
        },
        finally: function () {
        }
    })

}


function stopExperience() {
    var devices = []
    selectedCards().forEach(element => {
        devices.push(element.deviceId)
    });
    var body = { "devices": devices, "experience": document.getElementById("stop_choices_dropdown").value }
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

function disconnectSingleDevice(id){
    send({
        url: '/disconnect',
        start: function () {
            document.getElementById("disconnectButton").classList.add("disabled");
        },
        success: function () {
            showStatus("Device(s) have been disconnected");
            setTimeout(function () {
                location.reload();
            }, 3000);
        },
        devices: [id],
        problem: function (error) {
            showStatus("Error disconnecting devices: " + error);
        },
        finally: function () {
            document.getElementById("disconnectButton").classList.remove("disabled");
        }
    })
}

function disconnectDevice() {

    send({
        url: '/disconnect',
        start: function () {
            document.getElementById("disconnectButton").classList.add("disabled");
        },
        success: function () {
            showStatus("Device(s) have been disconnected");
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

function restartDevice() {

    send({
        url: '/restart',
        start: function () {
            document.getElementById("restartButton").classList.add("disabled");
        },
        success: function () {
            showStatus("Device(s) have been restarted");
            setTimeout(function () {
                location.reload();
            }, 3000);
        },
        problem: function (error) {
            showStatus("Error restarting devices: " + error);
        },
        finally: function () {
            document.getElementById("restartButton").classList.remove("disabled");
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
        this.attachShadow({ mode: 'open' });
        var bootstrapStyles = document.createElement('link')
        bootstrapStyles.rel = 'stylesheet'
        bootstrapStyles.href = 'static/bootstrap-5.2.0-beta1-dist/css/bootstrap.css'
        this.shadowRoot.appendChild(bootstrapStyles);
        this.shadowRoot.appendChild(document.querySelector("#device-card").content.cloneNode(true));
        this.image = image;
        this.deviceId = device['id'];
        this.device_icon = device['icon'];
        this.selected = selected;
        this.updateMessage(device['message']);
        this.updated = undefined;
        var checkbox = this.shadowRoot.getElementById("cardSelect");


        checkbox.addEventListener('change', () => {
            if (checkbox.checked) {
                this.updateSelected(true)
            } else {
                this.updateSelected(false)
            }
        })

        if (this.device_icon && this.device_icon['col']) {
            var el = this.shadowRoot.getElementById('setIcon');
            $(el).children('svg').remove();

            var col = this.device_icon['col'];
            var icon = this.device_icon['icon'];


            if (col) {
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
        }

        // setting this attribute on the nodes themselves to avoid future breakage during UI redesign
        for (var el_id of ['checkExperiences', 'stop_some_experience', 'setIcon', 'refresh-screen', 'wifi-connect']) {
            var el = this.shadowRoot.getElementById(el_id);
            // should really be setting data-device_id
            el.setAttribute('device_id', this.deviceId)
        }

        if (this.deviceId.split('.').length > 2) {
            var el = this.shadowRoot.getElementById('wifi-connect');
            el.hidden = true;
        }

        var check_battery_mins_wait = 5;
        this.getBatteryPercentage()
        this.batteryInterval = setInterval(() => {
            this.getBatteryPercentage()
        }, check_battery_mins_wait * 60 * 1000);

    }

    kill() {
        clearInterval(this.batteryInterval);
    }

    updated_recently(){
        if(!this.updated){
            this.updated = new Date().getTime();
            return false;
        }
        var difference = (new Date().getTime() - this.updated) / 1000;
        var grace_period_after_headset_dies_s = 1;
        return difference < grace_period_after_headset_dies_s;
    }

    just_updated() {
        this.updated = new Date().getTime();
    }

    update_icon(icon, text) {
        if (icon) {
            var find_icon = this.shadowRoot.getElementById("setIcon");
            var svg_parent = $(find_icon).find('svg').parent()
            $(svg_parent).children('svg').remove();
            $(svg_parent).append(icon);
        }
        var el_text = this.shadowRoot.getElementById('device-name');
        $(el_text).text(text);
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

    updateMessage(str) {
        var el = this.shadowRoot.getElementById("message");
        if (str && str.length > 0) {
            el.hidden = false;
        } else {
            el.hidden = true;
        }
        el.innerHTML = str;
    }

    check_screenshots_enabled_and_now_remove_image() {

        if(defaults.screenshots_enabled) return false;
        if(this.image !==''){
            this.shadowRoot.querySelector("img").src = '';
            this.image = '';
            return true;
        }
        return false;
    }

    updateImage64(image64) {
        this.image = image64;
        this.just_updated();
        this.shadowRoot.querySelector("img").src = "data:image/png;base64, " + image64;
    }

    connectedCallback() {
        this.shadowRoot.querySelector("img").src = this.image;
        var device_name = this.shadowRoot.querySelector("#device-name");

        if (this.device_icon && this.device_icon['text']) {
            var text = this.device_icon['text'];
            if (text.length > 0) device_name.innerHTML = text;

        } else {
            device_name.innerHTML = this.deviceId;
        }

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

    api.card_map = card_map;

    api.refresh_devices = function () {
        location.reload();
    }

    api.set_icon = function (device_id, icon, text) {
        var device = card_map[device_id];
        device.update_icon(icon, text);
    }

    api.wifi_connect = function (el) {

        var device_id = el.getAttribute('device_id');
        var orig_text = el.innerHTML;
        el.innerHTML = 'please wait';
        el.classList.add('disabled');
        fetch("connect/" + device_id)
            .then(function (response) {
                return response.json()
            })
            .then(function (json) {
                if (json['success']) {
                    showStatus(json['message']);
                    json['message'] = '';
                    // below causing troubles
                    //devices_manager.check_add_cards([json, ])
                } else {
                    showStatus(json['error']);
                }
            })
            .catch(function (err) {
                console.log('error with wifi connecting device ' + device_id, err);
            })
            .finally(function () {
                el.innerHTML = orig_text;
                el.classList.remove('disabled');
            });
    }

    api.refresh_image = function (el) {
        var device = el.getAttribute('device_id');
        if (card_map[device].check_screenshots_enabled_and_now_remove_image() === true) return;

        fetch("device-screen/" + rate + "/" + image_height + "/" + device)
            .then(function (response) {
                return response.json()
            })
            .then(function (json) {
                if (json['base64_image']) {
                    var b64_image = json['base64_image'];
                    card_map[device].updateImage64(b64_image);
                }
            })
            .catch(function () {
                console.log('error with polling for device ' + device)
            });

    }

    function screengrab_polling(device, on) {
        if(defaults.screenshots_enabled === 0) return;
        if (on === undefined) on = true;

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

        function poll(do_timeout) {
            if (do_timeout === undefined) do_timeout = true;
            if (lock) {
                return
            }
            lock = true
            fetch("device-screen/" + rate + "/" + image_height + "/" + device)
                .then(function (response) {
                    return response.json()
                })
                .then(function (json) {
                    if (json['base64_image']) {
                        var b64_image = json['base64_image'];
                        card_map[device].updateImage64(b64_image);
                    } else if (json['device-offline']) {
                        remove_card(device);
                    }
                })
                .catch(function () {
                    console.log('error with polling for device ' + device)
                    //api.refresh_devices()
                })
                .finally(function () {
                    if (card_map[device]) {
                        if (do_timeout) card_map[device]['poll'] = setTimeout(poll, rate);
                    }
                    lock = false;
                })
        }
    }

    function remove_card(card_id) {
        var card = card_map[card_id];
        if(card.updated_recently()){
            console.log('buffer keeping card alive for a short while: ' + card_id);
            return
        }
        //
        screengrab_polling(card_id, false);

        card.kill();
        delete card_map[card_id];
        var i = cardList.indexOf(card_id);
        cardList.splice(i, 1);
        document.querySelector("#main-container").removeChild(card);
    }

    function get_devices() {
        console.log('polling for new devices')
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
                api.check_add_cards(json['devices']);
            })
            .catch(function (error) {
                console.log(error);
            })
    }

    get_devices();
    setInterval(get_devices, defaults.check_for_new_devices_poll);

    api.check_add_cards = function(my_devices){
        if (my_devices.length > 0) {
            var found = document.getElementById('no-devices');
            if (found) found.remove();
        }
        var devices_so_far = Object.keys(card_map);

        for (var device of my_devices) {

            var device_id = device['id'];
            var found_at = devices_so_far.indexOf(device_id);
            var card;
            if (found_at === -1) {
                var placeholder = "/static/images/placeholder.jpg";
                if(!defaults.screenshots_enabled) placeholder =  '';
                card = new DeviceCard(placeholder, device, false);
                card.classList.add('col')
                cardList.push(card);
                document.querySelector("#main-container").prepend(card);
                card_map[device_id] = card
                screengrab_polling(device_id, true);
            } else {
                card = card_map[device_id];
                card.updateMessage(device['message']);
                card.just_updated();
                devices_so_far.splice(found_at, 1);
            }
        }
        for (var d_missing of devices_so_far) {
            remove_card(d_missing);
        }
    }

    api.devices = function () {
        return card_map.keys;
    }

    return api;
}
    ();

var checkSelected = () => {
    if (selectedCards().length !== 0) {
        var el = document.getElementById("navContainer");
        if (el) document.getElementById("navContainer").innerHTML = "";
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
            body: { 'volume': volume },
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
    var el_name = $(el).find('#device-name').text();
    $('#setIconModalLabel').val(el_name);
    $(icon_modal).modal('show');

    function icon_modal_helper() {
        // put your default event here
        $(icon_modal).modal('hide');
        var selected = $("input[type='radio'][name='icon-options']:checked");
        var col = 'none';
        var icon = 'none';
        var cloned_icon = '';

        if (selected.length > 0) {
            col = $(selected[0]).data('col');
            icon = $(selected[0]).data('icon');
            cloned_icon = $(selected.parent().find('svg')[0]).clone();
            cloned_icon.css('color', col);
        }
        var el_text = $('#setIconModalLabel').val();
        if (el_text.length < 3) el_text += 'name too short'
        devices_manager.set_icon(device_id, cloned_icon, el_text);
        if (!col) col = 'none'
        if (!icon) icon = 'none'
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
        })

    }

    $('.icon-set, #close-set-icon-modal').on("click", icon_modal_helper);
}

function stop_some_experience(el) {

    var device = el.getAttribute('device_id');

    send({
        body: { 'experience': '?' },
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

function experience_command(el, cmd, experience, devices, success_message, error_message) {
    if (!experience) experience = $(el).closest('li').data('experience');
    var device = $(el).closest('.list-group').data('device');
    if (device === undefined || device.length === 0) device = 'ALL'

    send({
        body: { 'experience': experience, 'devices': devices },
        start: function () {
        },
        url: '/command/' + cmd + '/' + device,
        success: function (data) {

            if (data['message']) showStatus(data['message'])
            else {
                if (!success_message) success_message = "Experience has " + cmd + "ed!"
                if (data['message']) success_message += ' ' + data['message']
                showStatus(success_message);
            }


        },
        problem: function (error) {
            if (data['message']) showStatus(data['message'])
            else {
                if (!error_message) error_message = "Error " + cmd + "ing experience: " + error;
                showStatus(error_message + error['message']);
            }
        },
        finally: function () {

        }
    })
}

function test_many(){
    var found = $('device-card').length - 1;

    if(found<0) return
    var i =Math.round(Math.random() * found);
    var device_bit = $($('device-card')[i].shadowRoot);
    $(device_bit).find('#checkExperiences').click();

    setTimeout(function(){
    $('#experiences-modal-close').click();
    var exp_found = $('#experiences_modal_content').find('.bi-play-fill').length -1;
    if(exp_found<0) return
    i =Math.round(Math.random() * exp_found);
    var el = $($('#experiences_modal_content').find('.bi-play-fill')[i]);

    var cmd = 'start';

    var experience = $(el).closest('li').data('experience');
    var device = $(el).closest('.list-group').data('device');
    console.log('starting experience', experience, device);
    send({
        body: { 'experience': experience},
        start: function () {
        },
        url: '/command/' + cmd +'/' + device,
        success: function (data) {
            showStatus("Experience has " + cmd + "ed!");

        },
        problem: function (error) {
            showStatus("Error " + cmd + "ing experience: " + error);
        },
        finally: function () {
            setTimeout(function(){
                console.log('stopping experience', experience, device);
                send({
                    body: { 'experience': '?' },
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
                        setTimeout(function(){
                            test_many();
                        },5000);
                    }
                })
            }, 5000)

        }
    }
    )
    }, 1000);
}

