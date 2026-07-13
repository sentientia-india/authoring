document.querySelectorAll(".demo-card").forEach(function (card) {
  card.querySelector(".demo-check").addEventListener("click", function () {
    var selected = card.querySelector("input:checked");
    var feedback = card.querySelector(".demo-feedback");
    if (!selected) {
      feedback.className = "demo-feedback caution";
      feedback.textContent = "Choose a response before checking your decision.";
      return;
    }
    var correct = selected.value === card.dataset.answer;
    feedback.className = "demo-feedback " + (correct ? "correct" : "incorrect");
    feedback.textContent = correct
      ? "Strong decision. This controls immediate risk and preserves the evidence needed for the next step."
      : "Not quite. Look for the response that controls risk, validates the outcome, and supports the next decision.";
  });
});
