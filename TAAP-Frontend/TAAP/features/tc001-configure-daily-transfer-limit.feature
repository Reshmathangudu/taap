@sdet @bdd @TC001 @REQ101 @SCRUM-13 @SCRUM-10 @daily-limit @integration @automated
Feature: Configure daily transfer limit
  As a retail banking user
  I want to update the daily transfer limit for a beneficiary
  So that future transfers are validated against the configured daily limit

  # Source: Jira test case SCRUM-13 / TC-001
  # Linked requirement: REQ-101
  # Linked story: SCRUM-10 - Configure daily beneficiary limit

  Background:
    Given the retail banking user is logged in successfully
    And the user has access to daily limit configuration
    And the daily limit feature is enabled
    And the current daily transfer limit is available

  Scenario Outline: Configure daily transfer limit with a valid amount
    Given the user's current daily transfer limit is <currentDailyLimit> <currency>
    And the allowed daily transfer limit range is <minimumAllowedLimit> <currency> to <maximumAllowedLimit> <currency>
    When the user navigates to the daily limit configuration page
    And the user views the current daily transfer limit
    And the user enters <newDailyLimit> <currency> as the new daily transfer limit
    And the user submits the updated daily transfer limit
    Then the system should accept the new daily transfer limit
    And a success confirmation message should be displayed
    And the updated daily transfer limit should be shown as <newDailyLimit> <currency>
    And the new daily transfer limit should be available for future transfer validation

    Examples:
      | currentDailyLimit | newDailyLimit | minimumAllowedLimit | maximumAllowedLimit | currency |
      | 50000             | 75000         | 10000               | 100000              | INR      |
