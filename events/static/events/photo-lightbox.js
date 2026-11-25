"use strict";

/* Show an event picture in a viewer people can close, instead of opening the raw image. */
(() => {
    const dialog = document.querySelector("[data-photo-lightbox-dialog]");
    if (!dialog || typeof dialog.showModal !== "function") return;

    const image = dialog.querySelector("[data-photo-lightbox-image]");
    const caption = dialog.querySelector("[data-photo-lightbox-caption]");
    const closeButton = dialog.querySelector("[data-photo-lightbox-close]");
    const error = dialog.querySelector("[data-photo-lightbox-error]");
    const retry = dialog.querySelector("[data-photo-lightbox-retry]");
    if (!image || !caption || !closeButton || !error || !retry) return;

    let opener = null;

    function load(url) {
        error.hidden = true;
        image.hidden = false;
        retry.href = url;
        image.src = url;
    }

    document.addEventListener("click", (event) => {
        const target = event.target;
        const link = target && typeof target.closest === "function"
            ? target.closest("[data-photo-lightbox]")
            : null;
        // Leave new-tab, download and other modified clicks to the browser.
        if (!link || event.defaultPrevented || event.button !== 0 ||
            event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

        event.preventDefault();
        opener = link;
        load(link.href);
        image.alt = link.dataset.photoAlt || "";
        caption.textContent = link.dataset.photoCaption || "";
        dialog.showModal();
        closeButton.focus();
    });

    closeButton.addEventListener("click", () => dialog.close());

    // A storage outage answers with an error page, not a picture: say so and offer a retry.
    image.addEventListener("error", () => {
        if (!dialog.open || !image.getAttribute("src")) return;
        image.hidden = true;
        error.hidden = false;
    });

    retry.addEventListener("click", (event) => {
        event.preventDefault();
        const url = retry.href;
        image.removeAttribute("src");
        load(url);
    });

    // A click on the dimmed area outside the picture lands on the dialog itself.
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
    });

    // Escape closes the dialog natively; every way out ends here.
    dialog.addEventListener("close", () => {
        image.removeAttribute("src");
        error.hidden = true;
        image.hidden = false;
        if (opener) opener.focus();
        opener = null;
    });
})();
