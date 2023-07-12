function go_to_action(placeholder) {
    // go to a link that requires filling in a placeholder value
    let id = document.getElementById("id").value;
    let format_string = document.getElementById("action").value;
    let url = format_string.replaceAll(placeholder, id);
    window.location.href = url;
}

function call_special_action(url, action) {
    // call an endpoint in the background, showing an alert if it fails
    fetch(url).then(
        (response) => {
            if (response.status != 200) {
                alert(action + " failed");
            }
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

function create_tag_form(parent_id, name, known_id, tags) {
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
}

function add_tag(name) {
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
    } else {
        alert("Invalid tag name: '" + tag_name + "'");
    }

    return false;
}

function remove_tag(name) {

    select = document.getElementById(name);

    options = select.children;
    for (i = 0; i < options.length; i++) {
        if (options[i].selected) {
            options[i].remove();
        }
    }
}

function select_all() {
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