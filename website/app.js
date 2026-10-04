// A deterministic word sketch. It never requests microphone access or runs inference.
const examples = {
  message: [
    "hey um let’s take the long way home",
    "Hey, let’s take the long way home.",
  ],
  idea: [
    "what if we made a little room for the unexpected",
    "What if we made a little room for the unexpected?",
  ],
  reminder: [
    "remember to bring the notebook not the laptop",
    "Remember to bring the notebook, not the laptop.",
  ],
};
const spoken = document.getElementById("spoken");
const written = document.getElementById("written");
document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    const example = examples[button.dataset.example];
    if (!example || !spoken || !written) return;
    spoken.textContent = example[0];
    written.textContent = example[1];
    document.querySelectorAll("[data-example]").forEach((item) => {
      item.setAttribute("aria-pressed", String(item === button));
    });
  });
});
