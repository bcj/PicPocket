{% whitespace all %}
var last_removed = undefined;

function go_to_action(placeholder) {
    // go to a link that requires filling in a placeholder value
    let id = document.getElementById("id").value;
    let format_string = document.getElementById("action").value;
    let url = format_string.replaceAll(placeholder, id);
    window.location.href = url;
}

function call_special_action(url, action, callback=undefined) {
    // call an endpoint in the background, showing an alert if it fails
    fetch(url).then(
        (response) => {
            if (response.status != 200) {
                alert(action + " failed");
            } else if (callback) {
                callback(response)
            }
        }
    );
}

function file_dialog_from_key(urls, key_id, input_id, form_id=undefined) {
    url = urls[document.getElementById(key_id).value];
    file_dialog(url, input_id, form_id);
}

function file_dialog(url, input_id, form_id=undefined) {
    call_special_action(
        url,
        "file dialog",
        (response) => {
            element = document.getElementById(input_id);
            response.text().then(
                (text) => {
                    element.setAttribute("value", text);

                    if (form_id) {
                        document.getElementById(form_id).submit();
                    }
                }
            );
        }
    );
}

// tagging
function create_tag_list(id, tag_list) {
    // create a datalist containing a list of tags
    datalist = document.createElement("datalist");
    datalist.id = "known-tags";
    for (tag of tag_list) {
        option = document.createElement("option");
        option.setAttribute("value", tag);
        datalist.appendChild(option);
    }
    document.getElementById(id).appendChild(datalist);

    return datalist.id;
}

function create_tag_form(
    parent_id, name, known_id, tags, suggestions = undefined, default_suggestions = undefined
) {
    parent = document.getElementById(parent_id);

    add_form = document.createElement("form");
    add_form.id = "add-tag-form-" + name;
    add_form.setAttribute("class", "tag-form");

    input = document.createElement("input");
    input.id = "add-tag-" + name;
    input.setAttribute("class", "add-text");
    input.setAttribute("form", add_form.id);
    input.setAttribute("type", "text");
    input.setAttribute("list", known_id);
    add_form.appendChild(input);

    button = document.createElement("input");
    button.setAttribute("class", "add-button")
    button.setAttribute("type", "submit");
    button.setAttribute("form", add_form.id);
    button.setAttribute("value", "add");
    add_form.appendChild(button);

    add_form.setAttribute("onsubmit", "return add_tag('" + name + "')");
    parent.appendChild(add_form);

    select = document.createElement("select");
    select.id = name;
    select.setAttribute("name", name);
    select.setAttribute("class", "tag-list");
    select.setAttribute("multiple", true);

    for (tag of tags) {
        option = document.createElement("option");
        option.setAttribute("value", tag);
        option.appendChild(document.createTextNode(tag));
        select.appendChild(option);
    }

    parent.appendChild(select);

    button = document.createElement("button");
    button.appendChild(document.createTextNode("remove"));
    button.setAttribute("type", "button");
    button.setAttribute("onclick", "remove_tag('" + name + "')");
    parent.appendChild(button);

    if (
        (default_suggestions != undefined && default_suggestions.length > 0)
        || (suggestions != undefined && suggestions.length > 0)
    ) {
        if (default_suggestions == undefined) {
            default_suggestions = [];
        }

        if (suggestions == undefined) {
            suggestions = [];
        }

        suggestion_form = document.createElement("form")
        suggestion_form.id = "suggest-tag-form-" + name;
        suggestion_form.setAttribute("class", "suggestion");
        suggestion_form.setAttribute("onsubmit", "return add_suggested_tag('" + name + "')");

        label = document.createElement("label")
        label.setAttribute("for", "suggest-" + name)
        label.setAttribute("class", "suggestion");
        label.appendChild(document.createTextNode("Suggestions:"));
        suggestion_form.appendChild(label)

        select = document.createElement("select");
        select.id = "suggest-" + name;
        select.setAttribute("name", select.id);
        select.setAttribute("class", "tag-list suggestion");
        select.setAttribute("multiple", true);
        select.setAttribute("height", Math.min(default_suggestions.length + suggestions.length, 10))

        for (tag of default_suggestions) {
            option = document.createElement("option");
            option.setAttribute("value", tag);
            option.setAttribute("selected", true);
            option.appendChild(document.createTextNode(tag));
            select.appendChild(option);
        }

        for (tag of suggestions) {
            option = document.createElement("option");
            option.setAttribute("value", tag);
            option.appendChild(document.createTextNode(tag));
            select.appendChild(option);
        }

        suggestion_form.appendChild(select);

        button = document.createElement("button");
        button.setAttribute("class", "suggestion");
        button.appendChild(document.createTextNode("add"));
        button.setAttribute("type", "button");
        button.setAttribute("onclick", "add_suggested_tag('" + name + "')");
        suggestion_form.appendChild(button);

        parent.appendChild(suggestion_form);
    }
}

function add_tag(name, show_alert = true) {
    input = document.getElementById("add-tag-" + name);

    tag_name = input.value;
    // don't let a tag start/end with whitespace + slashes only inbetween
    if (/^([^/ ]([^/]*[^/ ])?)(?:\/[^/ ]([^/]*[^/ ])?)*$/u.exec(tag_name)) {
        select = document.getElementById(name);

        options = select.children;
        matching = false;
        for (i = 0; i < options.length; i++) {
            if (options[i].value == tag_name) {
                matching = true;
                break;
            }
        }

        if (!matching) {
            option = document.createElement("option");
            option.setAttribute("value", input.value);
            option.appendChild(document.createTextNode(input.value));
            select.appendChild(option);
        }

        input.value = "";
        last_removed = undefined;
    } else if (show_alert) {
        alert("Invalid tag name: '" + tag_name + "'");
    }

    return false;
}

function add_suggested_tag(name) {
    input = document.getElementById("suggest-" + name);
    select = document.getElementById(name);

    to_move = [];
    count = 0;
    for (option of input.children) {
        if (option.selected) {
            option.selected = false;

            matching = false;
            for (existing of select.children) {
                if (existing.value == option.value) {
                    matching = true;
                    break;
                }
            }

            if (!matching) {
                to_move.push(option);
            }
        } else {
            count += 1;
        }
    }

    for (option of to_move) {
        select.appendChild(option)
    }

    if (count == 0) {
        document.getElementById("suggest-tag-form-" + name).remove();
    }

    return false;
}

function remove_tag(name) {
    select = document.getElementById(name);

    to_remove = [];
    for (option of select.children) {
        if (option.selected) {
            to_remove.push(option);
        }
    }

    if (to_remove.length == 1) {
        input = document.getElementById("add-tag-" + name);
        if (input && !input.value) {
            last_removed = input.value = to_remove[0].value;
        }

        to_remove[0].remove();
    } else {
        for (option of to_remove) {
            option.remove();
        }
    }
}

function select_all(name = undefined) {
    if (name) {
        input = document.getElementById("add-tag-" + name);
        if (input.value && input.value != last_removed) {
            add_tag(name, false);
        }
    }

    selects = document.getElementsByClassName("tag-list");
    if (selects) {
        for (select of selects) {
            for (option of select.children) {
                option.selected = true;
            }
        }
    }

    return true;
}