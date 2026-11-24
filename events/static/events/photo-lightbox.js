"use strict";

/* Show an event picture in a viewer people can close, instead of opening the raw image. */
(() => {
    const dialog = document.querySelector("[data-photo-lightbox-dialog]");
    if (!dialog || typeof dialog.showModal !== "function") return;

    const image = dialog.querySelector("[data-photo-lightbox-image]");
    const caption = dialog.querySelector("[data-photo-lightbox-caption]");
    const closeButton = dialog.querySelector("[data-photo-lightbox-close]");
    if (!image || !caption || !closeButton) return;

    let opener = null;

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
        image.src = link.href;
        image.alt = link.dataset.photoAlt || "";
        caption.textContent = link.dataset.photoCaption || "";
        dialog.showModal();
        closeButton.focus();
    });

    closeButton.addEventListener("click", () => dialog.close());

    // A click on the dimmed area outside the picture lands on the dialog itself.
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
    });

    // Escape closes the dialog natively; every way out ends here.
    dialog.addEventListener("close", () => {
        image.removeAttribute("src");
        if (opener) opener.focus();
        opener = null;
    });
})();
