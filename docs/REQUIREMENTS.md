# Requirements

## Phase 1 scope

Phase 1 contains only:

1. Basic school configuration
2. Academic Year management
3. Class/Grade management
4. Section management
5. Applicant management
6. Guardian records and relationships
7. Admission decision
8. Explicit progression of an accepted Applicant into Student
9. Academic Enrollment
10. Class + Section assignment through enrollment
11. Student status
12. Student profile
13. Basic student search/listing
14. Initial administrative authorization/permissions
15. Appropriate timestamps/history where required

## Explicitly out of scope for Phase 1

- attendance
- fees
- payment gateways
- examinations/results
- timetable
- teacher portal
- parent portal
- student portal
- messaging integrations
- automated email
- library
- transport
- HR/payroll
- hostel
- inventory
- mobile app
- advanced analytics
- AI features

## Terms and lifecycle rules

FROZEN:

- **Applicant** and **Student** are different domain concepts with different lifecycle meanings.
- An Applicant is an application record and is not a Student merely because the application exists or is reviewed.
- **Student** is the separate, long-lived school identity created through the explicit progression workflow.
- **Academic Enrollment** connects a Student, Academic Year, Class/Grade, Section, and enrollment/status information. It represents academic placement; Class/Grade and Section are not permanent mutable Student identity fields.
- School operational records are historical records. Important historical information must not be silently overwritten or casually hard-deleted.

## Administrative authorization

FROZEN: Authorization must be designed from the beginning. Phase 1 must not treat every authenticated account as an administrator.

Acceptance criteria:

- A user must have appropriate administrative authorization to perform Phase 1 administrative mutations, including school configuration, academic setup, applicant decisions, Applicant-to-Student progression, enrollment changes, and guardian relationship changes.
- An unauthorized user cannot perform those protected mutations.
- Authorization is verified by automated tests for critical Phase 1 operations.
- Phase 1 need not implement complete workflows for future Teacher, Staff, Parent/Guardian, or Student roles.

## School configuration

Phase 1 provides only the minimum school configuration needed to establish the school context for administrative operation. It does not introduce extensive settings or multi-school SaaS behavior.

Acceptance criteria:

- An authorized administrator can establish and view the school's basic configuration.
- The configuration required by the approved Phase 1 workflows is present and valid before it is relied upon by those workflows.
- Unauthorized users cannot change the school configuration.

## Academic Year management

Academic Years/sessions are explicit domain records. Historical records remain associated with their original Academic Year.

Acceptance criteria:

- An authorized administrator can create and view an Academic Year.
- An Academic Year has meaningful date validation: a start date and end date are required, and the end date must be later than the start date.
- Invalid dates are rejected without creating or partially changing an Academic Year.
- Academic Years that have historical associated records remain preserved; they are not silently removed or repurposed.
- A record associated with an Academic Year is not silently moved to a different Academic Year by editing or creating another Academic Year.
- Unauthorized users cannot create or change Academic Years.

## Class/Grade management

Classes/Grades are explicit records. Phase 1 does not prescribe a country-specific naming convention.

Acceptance criteria:

- An authorized administrator can create and view Class/Grade records.
- Required Class/Grade information is validated before creation or change.
- Class/Grade records used by historical Academic Enrollments are not casually hard-deleted or silently repurposed in a way that changes historical placement.
- Unauthorized users cannot create or change Class/Grade records.

## Section management

Sections are explicit records associated with the appropriate class and academic structure. A Student's section membership is represented by Academic Enrollment, not by permanently mutating Student identity.

Acceptance criteria:

- An authorized administrator can create and view a Section in its appropriate Class/Grade context.
- A Section cannot be created without the required valid Class/Grade relationship.
- Section membership shown for a Student comes from the relevant Academic Enrollment.
- A Section used by historical Academic Enrollments is not casually hard-deleted or silently repurposed in a way that changes historical placement.
- Unauthorized users cannot create or change Sections.

## Applicant management

Applicants are application records, distinct from Students. Phase 1 supports registration, review, and an explicit admission decision; it does not require a more complex admissions workflow.

Acceptance criteria:

- An authorized administrator can create and view an Applicant.
- Creating an application does not create a Student.
- The application admission state is explicit and changes only through an explicit admission decision.
- Application history remains available, including after an admission decision or Applicant-to-Student progression.
- Invalid or conflicting admission operations are rejected without creating a Student or silently changing the application history.
- Unauthorized users cannot create or change Applicants or admission state.

## Guardian records and relationships

Guardians are first-class records. Guardian relationships carry a relationship type.

Acceptance criteria:

- An authorized administrator can create and view Guardian records.
- A Guardian may be recorded while an Applicant is being managed; recording that Guardian does not create a Student. The Student–Guardian association is established when a Student exists.
- An authorized administrator can associate one Student with multiple Guardians and one Guardian with multiple Students.
- Each Student–Guardian association records a relationship type.
- When siblings share a Guardian, the existing Guardian record can be associated with each Student; the workflow does not require duplicate Guardian records merely because the Guardian has multiple children.
- Invalid relationship operations, including those missing a required Student, Guardian, or relationship type, are rejected without creating a partial association.
- Unauthorized users cannot change Guardian records or relationships.

## Admission decision

Phase 1 supports the explicit decisions **accepted** and **rejected**. It does not introduce additional admission states unless already approved in project documentation.

Acceptance criteria:

- An authorized administrator can explicitly record an accepted or rejected decision for an Applicant.
- A rejected Applicant cannot progress to Student through the Phase 1 workflow.
- Recording an acceptance or rejection does not destroy the original Applicant record.
- Repeating or conflicting decisions is handled explicitly; it must not silently create a Student or erase the prior application history.
- Unauthorized users cannot record an admission decision.

## Explicit Applicant-to-Student progression

Progression is a deliberate administrative workflow, separate from application creation and admission review.

Acceptance criteria:

- Only an appropriately accepted Applicant may progress to Student.
- An Applicant does not become a Student automatically merely because the Applicant exists, is reviewed, or is accepted.
- An authorized administrator can explicitly progress an accepted Applicant into a separate Student record.
- The original Applicant remains historically accessible after progression.
- The resulting Student is a long-lived school identity, separate from academic-year-specific placement.
- The workflow prevents duplicate accidental Student creation from the same Applicant where reasonably possible; a repeated progression attempt must not silently create another Student.
- An invalid progression attempt, including one for a missing, rejected, or not-accepted Applicant, is rejected without creating a Student.
- Unauthorized users cannot progress an Applicant to Student.

## Academic Enrollment and assignment

Academic Enrollment is the required record for a Student's academic placement. It connects Student, Academic Year, Class/Grade, Section, and appropriate enrollment/status information.

Acceptance criteria:

- An authorized administrator can create and view an Academic Enrollment for a Student.
- An Academic Enrollment requires valid relationships to a Student, Academic Year, Class/Grade, and Section, plus the required enrollment/status information.
- The Section selected for an enrollment must belong to the enrollment's selected Class/Grade.
- An enrollment missing required relationships, using incompatible class/section/year relationships, or otherwise conflicting with the approved placement rules is rejected without a partial enrollment.
- A Student may accumulate multiple Academic Enrollments over time.
- A later class, section, or Academic Year change creates or updates the appropriate enrollment without overwriting prior Academic Enrollment history.
- The Student's current academic placement is derived from the appropriate active/current Academic Enrollment, rather than by rewriting historical Student data.
- Unauthorized users cannot create or change Academic Enrollments.

## Student status

Student status must support the approved student lifecycle without creating an expansive workflow. The exact Phase 1 status list is not frozen by approved documentation; the implementation plan must define only the minimum statuses necessary for that lifecycle.

Acceptance criteria:

- An authorized administrator can view a Student's relevant status and make permitted status changes.
- Status changes are validated according to the defined minimum lifecycle and do not silently alter unrelated historical enrollment or application data.
- Unauthorized users cannot change Student status.

## Student profile

The Phase 1 Student profile is an administrative view of the Student's lifecycle and current placement, not a portal or later operational module.

Acceptance criteria:

- An authorized administrator can view a Student profile containing student identity information, linked Guardian information, current Academic Enrollment, and relevant Student status.
- Where Phase 1 enrollment history exists, the profile shows historical Academic Enrollments in addition to the current placement.
- The profile does not require attendance, fees, results, timetable, messaging, or other out-of-scope data.
- Unauthorized users cannot access protected administrative Student profile information.

## Basic student search/listing

Phase 1 provides a basic administrative student list and enough search capability for administrators to find Students reliably. It does not include advanced analytics, reporting, or dashboards.

Acceptance criteria:

- An authorized administrator can view a list of Students and search it using available Student identity information.
- Search results identify the matching Student sufficiently to select and open the Student profile.
- The list/search does not create, alter, or infer academic history.
- Unauthorized users cannot access protected administrative Student listings or searches.

## Historical integrity, timestamps, and failure behavior

Acceptance criteria:

- The original Applicant record remains available after progression to Student.
- Previous Academic Enrollments remain available after a Student later changes Class/Grade, Section, or Academic Year.
- Important operational records are not casually hard-deleted; where correction is required, it must not silently rewrite unrelated historical information.
- Required creation and change timestamps/history are retained where needed to support the approved lifecycle and historical principles.
- Critical invalid paths—including invalid Academic Year dates, invalid Applicant progression, incomplete or incompatible Academic Enrollment, unauthorized mutation, and applicable duplicate/conflicting operations—fail clearly without partial or unintended records.

## Phase 1 acceptance journey

An authorized administrator can complete this journey:

Configure school
→ create Academic Year
→ create Class/Grade and Section
→ register Applicant
→ associate Guardian
→ review application
→ accept Applicant
→ explicitly create/progress Student
→ create Academic Enrollment
→ assign Academic Year + Class/Grade + Section
→ view active/current Student profile

Successful completion requires that the Student was not created by application registration alone, the Applicant remains accessible, and current placement is represented through Academic Enrollment.

## Definition of Done

FROZEN: A feature or milestone is done when, where applicable:

- the approved requirement is satisfied
- the approved domain model is respected
- authorization is verified
- validation is verified
- important failure paths are tested
- database migrations are reviewed
- automated tests are added or updated and pass
- Django system checks pass
- Ruff checks pass
- build or deployment-relevant checks pass when introduced
- changed files are reviewed
- documentation is updated if behavior changes
- human business acceptance is completed

Do not impose an arbitrary code-coverage percentage. Testing should prioritize meaningful business rules, permissions, lifecycle transitions, integrity, and important contracts.
