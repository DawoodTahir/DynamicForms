// readability_wrapper.js
window.runReadability = () => {
    const article = new Readability(document.cloneNode(true)).parse();
    return article;
};
