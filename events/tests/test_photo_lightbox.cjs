// Run with: node --test events/tests/test_photo_lightbox.cjs
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const vm = require("node:vm");

const source = readFileSync(resolve(__dirname, "../static/events/photo-lightbox.js"), "utf8");

function listeners() {
    const handlers = {};
    return {
        handlers,
        addEventListener(name, handler) { handlers[name] = handler; },
    };
}

function setup({ supportsModal = true } = {}) {
    const doc = listeners();
    const image = {
        ...listeners(),
        src: "", alt: "", hidden: false, loads: [],
        removeAttribute(name) { this[name] = ""; },
        getAttribute(name) { return this[name]; },
    };
    // Record every picture the viewer asks the browser to fetch.
    let imageSrc = "";
    Object.defineProperty(image, "src", {
        get() { return imageSrc; },
        set(value) { imageSrc = value; if (value) image.loads.push(value); },
    });
    const caption = { textContent: "" };
    const error = { hidden: true };
    const retry = { ...listeners(), href: "" };
    const close = { ...listeners(), focus() { this.focused = true; } };
    const dialog = {
        ...listeners(),
        open: false,
        querySelector: (selector) => ({
            "[data-photo-lightbox-image]": image,
            "[data-photo-lightbox-caption]": caption,
            "[data-photo-lightbox-close]": close,
            "[data-photo-lightbox-error]": error,
            "[data-photo-lightbox-retry]": retry,
        })[selector],
        close() {
            this.open = false;
            this.handlers.close();
        },
    };
    if (supportsModal) dialog.showModal = function () { this.open = true; };
    const link = {
        href: "/events/photos/7/image/",
        dataset: { photoAlt: "Picture from Park Walk", photoCaption: "By Sam" },
        focus() { this.focused = true; },
    };
    link.closest = (selector) => (selector === "[data-photo-lightbox]" ? link : null);
    vm.runInNewContext(source, {
        document: { ...doc, querySelector: () => dialog },
    });
    function click(target, extra = {}) {
        const event = {
            target, button: 0, defaultPrevented: false,
            preventDefault() { this.defaultPrevented = true; this.prevented = true; },
            ...extra,
        };
        doc.handlers.click(event);
        return event;
    }
    return { doc, dialog, image, caption, close, error, retry, link, click };
}

test("opens the picture in the viewer instead of navigating away", () => {
    const ui = setup();
    const event = ui.click(ui.link);
    assert.equal(event.prevented, true);
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.image.src, "/events/photos/7/image/");
    assert.equal(ui.image.alt, "Picture from Park Walk");
    assert.equal(ui.caption.textContent, "By Sam");
    assert.equal(ui.close.focused, true);
});

test("the close button returns to the page and the picture link", () => {
    const ui = setup();
    ui.click(ui.link);
    ui.close.handlers.click();
    assert.equal(ui.dialog.open, false);
    assert.equal(ui.image.src, "");
    assert.equal(ui.link.focused, true);
});

test("clicking outside the picture closes the viewer", () => {
    const ui = setup();
    ui.click(ui.link);
    ui.dialog.handlers.click({ target: {} });
    assert.equal(ui.dialog.open, true);
    ui.dialog.handlers.click({ target: ui.dialog });
    assert.equal(ui.dialog.open, false);
});

test("modified clicks and other targets keep normal link behaviour", () => {
    const ui = setup();
    for (const extra of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { button: 1 }]) {
        assert.notEqual(ui.click(ui.link, extra).prevented, true);
    }
    assert.notEqual(ui.click({ closest: () => null }).prevented, true);
    assert.equal(ui.dialog.open, false);
});

test("browsers without dialog support fall back to the plain link", () => {
    const ui = setup({ supportsModal: false });
    assert.equal(ui.doc.handlers.click, undefined);
});

test("a picture that fails to load shows a message with a retry link", () => {
    const ui = setup();
    ui.click(ui.link);
    ui.image.handlers.error();
    assert.equal(ui.image.hidden, true);
    assert.equal(ui.error.hidden, false);
    assert.equal(ui.retry.href, "/events/photos/7/image/");

    const retryClick = { preventDefault() { this.prevented = true; } };
    ui.retry.handlers.click(retryClick);
    assert.equal(retryClick.prevented, true);
    assert.equal(ui.error.hidden, true);
    assert.equal(ui.image.hidden, false);
    assert.deepEqual(ui.image.loads, ["/events/photos/7/image/", "/events/photos/7/image/"]);
    assert.equal(ui.dialog.open, true);
});

test("closing after a failed load resets the viewer for the next picture", () => {
    const ui = setup();
    ui.click(ui.link);
    ui.image.handlers.error();
    ui.close.handlers.click();
    assert.equal(ui.error.hidden, true);
    assert.equal(ui.image.hidden, false);
    // Clearing the picture on close must not bring the message back.
    ui.image.handlers.error();
    assert.equal(ui.error.hidden, true);
    ui.click(ui.link);
    assert.equal(ui.error.hidden, true);
    assert.equal(ui.image.hidden, false);
});
