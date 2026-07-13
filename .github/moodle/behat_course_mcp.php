<?php
// Test-only Moodle Behat context for assertions inside player-hidden SCO frames.
require_once(__DIR__ . '/../../behat/behat_base.php');

class behat_course_mcp extends behat_base {
    /**
     * Assert raw DOM text in the currently selected frame without visibility filtering.
     *
     * @Then /^the current frame raw text should contain "(?P<text>(?:[^"]|\\")*)"$/
     */
    public function current_frame_raw_text_should_contain(string $text): void {
        $actual = (string)$this->getSession()->evaluateScript(
            'return document.body ? document.body.textContent : "";'
        );
        if (strpos($actual, $text) === false) {
            throw new RuntimeException("Raw frame text did not contain: {$text}");
        }
    }
}
