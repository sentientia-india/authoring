@mod @mod_scorm @_file_upload @_switch_iframe @course_mcp_acceptance
Feature: Course MCP packages retain tracked state in Moodle
  Background:
    Given the following "users" exist:
      | username | firstname | lastname | email |
      | student1 | Ari | Patel | ari@example.invalid |
    And the following "courses" exist:
      | fullname | shortname | category |
      | Course MCP conformance | CMCP | 0 |
    And the following "course enrolments" exist:
      | user | course | role |
      | student1 | CMCP | student |

  @javascript
  Scenario Outline: Track and restore a Course MCP SCORM package
    Given the following "activity" exists:
      | activity        | scorm |
      | course          | CMCP |
      | name            | <name> |
      | packagefilepath | <package> |
    When I am on the "<name>" "scorm activity" page logged in as student1
    And I press "Enter"
    And I switch to "scorm_object" iframe
    And I press "Run Moodle acceptance"
    Then I should see "Acceptance complete"
    And I wait "2" seconds
    And I switch to the main frame
    And I am on "Course MCP conformance" course homepage
    And I am on the "<name>" "scorm activity" page
    And I click on "Enter" "button" confirming the dialogue
    And I switch to "scorm_object" iframe
    And I should see "Restored acceptance marker"
    And I switch to the main frame
    And I am on homepage

    Examples:
      | name | package |
      | Course MCP SCORM 1.2 | mod/scorm/tests/packages/course-mcp-scorm-12.zip |
      | Course MCP SCORM 2004 | mod/scorm/tests/packages/course-mcp-scorm-2004.zip |
