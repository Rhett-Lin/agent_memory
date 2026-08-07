# Equivalence-audit judge/generator disagreements

Every sampled (task, memory) pair on which the independent Qwen2.5-7B judge (either wording) disagreed with the generator's structural P label. Text verbatim.

---
## family 29 (cal_finalize) pair A10 | wording A_same | generator=same judged=different

### task instruction
```
Ops note: finalize event 'Roadmap Workshop' (2026-10-01).
Policy: If no attendee of the event 'Roadmap Workshop' (2026-10-01) has declined (their RSVP count of 'declined' is 0), set the event status to 'confirmed' and insert a 'confirmation' notification addressed to the event's owner (use id 8101); otherwise set it to 'needs_review' and insert a 'warning' notification (id 8102).
Count RSVPs first, then write the event status and the owner notification (Bela Kowalski).
```
### memory card (A10, m_4c1faf37acfb)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Close out the ticket from the request once its subtasks are all complete.
Q: What must be true first? A: The request names the ticket key. The subtasks rows are linked to it in the subtasks table.
Q: How do we do it? A: Read the tickets row for the ticket key. Aggregate over the linked subtasks in the subtasks table. Count how many subtasks are still open. If none remain, mark the ticket 'resolved' and log a 'resolution' entry; otherwise, set the ticket to 'in_progress' and add a comment with the open count. Write the status update on the tickets row. Insert a matching entry into the ticket_events table (either order of the two writes is fine). Read the tickets row back and confirm before finishing.
Q: How do we know it worked? A: The ticket is resolved exactly when no open subtasks remain, with a matching log entry.
Q: What can go wrong? A: Never decide from the request text alone; run the aggregate yourself. Report the count you used if it is zero versus positive. Use a restrictive WHERE for every write.
```

---
## family 29 (cal_finalize) pair A01 | wording A_same | generator=different judged=same

### task instruction
```
Ops note: finalize event 'Roadmap Workshop' (2026-10-01).
Policy: If no attendee of the event 'Roadmap Workshop' (2026-10-01) has declined (their RSVP count of 'declined' is 0), set the event status to 'confirmed' and insert a 'confirmation' notification addressed to the event's owner (use id 8101); otherwise set it to 'needs_review' and insert a 'warning' notification (id 8102).
Count RSVPs first, then write the event status and the owner notification (Bela Kowalski).
```
### memory card (A01, m_b24ae5642a4f)
```
Retrieved experience - episode outcome: SUCCESS.
GOAL: Finalize the event from the request according to its RSVP list.
REQ: The request names the event title. / The attendees rows are linked to it in the attendees table.
DO: Read the events row for the event title. > Aggregate over the linked attendees in the attendees table. > Count how many attendees are already accepted. If at least one is accepted, set the event status to 'confirmed' and send the owner a 'confirmation' notification; otherwise, set it to 'needs_review' and send a 'warning' notification instead. > Write the status update on the events row. > Insert a matching entry into the notifications table (either order of the two writes is fine). > Read the events row back and confirm before finishing.
DONE WHEN: The event status and the owner's notification match the RSVP situation.
NEVER: Never decide from the request text alone; run the aggregate yourself. / Report the count you used if it is zero versus positive. / Use a restrictive WHERE for every write.
Note: Write the final values only after you have seen the current stored values with your own tools.
Note: Use the exact column names shown by the table listing.
```

---
## family 35 (cal_move_headcount) pair A10 | wording A_same | generator=same judged=different

### task instruction
```
Ops note: move 8 attendees of 'Training Briefing' from the morning session to the afternoon session (events table, date 2026-10-01).
Guard: morning >= 5 after the move; afternoon <= capacity 35.
Read both rows, check, update both, verify.
```
### memory card (A10, m_3a24a4042fa6)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Rebalance stock between the 'east' warehouse row and the 'west' warehouse row.
Q: What must be true first? A: The request states the amount to move and identifies both rows. Both rows exist in the stock table.
Q: How do we do it? A: Read the 'east' warehouse row row and the 'west' warehouse row row (either order). Check the guard: the 'east' warehouse row must keep at least the minimum keep level after the move, and the 'west' warehouse row must not exceed its capacity. Move the requested amount from the 'east' warehouse row into the 'west' warehouse row: subtract the amount from the 'east' warehouse row and add it to the 'west' warehouse row. If the guard fails, do not move anything and report the violation instead. Read both rows again and confirm the new values before finishing.
Q: How do we know it worked? A: The 'east' warehouse row is reduced and the 'west' warehouse row is increased by exactly the requested amount.
Q: What can go wrong? A: Never write before the guard check has passed. Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows. Always update both sides with a restrictive WHERE each.
```

---
## family 35 (cal_move_headcount) pair A01 | wording A_same | generator=different judged=same

### task instruction
```
Ops note: move 8 attendees of 'Training Briefing' from the morning session to the afternoon session (events table, date 2026-10-01).
Guard: morning >= 5 after the move; afternoon <= capacity 35.
Read both rows, check, update both, verify.
```
### memory card (A01, m_aeef7dfbe234)
```
Retrieved experience - episode outcome: SUCCESS.
GOAL: Rebalance headcount between the 'afternoon' session and the 'morning' session.
REQ: The request states the amount to move and identifies both rows. / Both rows exist in the events table.
DO: Read the 'afternoon' session row and the 'morning' session row (either order). > Check the guard: the 'afternoon' session must keep at least the minimum floor after the move, and the 'morning' session must not exceed its room capacity. > Move the requested amount from the 'afternoon' session into the 'morning' session: subtract the amount from the 'afternoon' session and add it to the 'morning' session. > If the guard fails, do not move anything and report the violation instead. > Read both rows again and confirm the new values before finishing.
DONE WHEN: The 'afternoon' session is reduced and the 'morning' session is increased by exactly the requested amount.
NEVER: Never write before the guard check has passed. / Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows. / Always update both sides with a restrictive WHERE each.
```

---
## family 24 (crm_escalate) pair A10 | wording A_same | generator=same judged=different

### task instruction
```
CRM maintenance request. A record for Farah Urbaniak (farah.urbaniak@demo.example.io) exists in the customers table. Policy: If the customer's complaint count is above the escalation threshold for tier 'silver' in the sla_policies table (column escalate_threshold), set status to 'escalated' and priority_flag to 1; otherwise, set status to 'routine' and priority_flag to 0. Verify the current complaint count in the database first, apply the update, then read the row back to confirm it.
```
### memory card (A10, m_e9d5796ea4e1)
```
Retrieved experience - episode outcome: SUCCESS.
In a past episode we handled this request: Apply the overstock policy to the stocked item from the request. Before starting, we made sure that: The request identifies the item's SKU. The stock table contains the matching row. This is how the episode went. Step 1: Read the stock row for the item's SKU. Step 2: Find the applicable overstock limit from the inv_policies table in the inv_policies table (match the product category and read overstock_limit). Step 3: Compare the row's on-hand quantity with the overstock limit from the inv_policies table. Step 4: If the on-hand quantity is above the overstock limit from the inv_policies table, set flag to 'markdown' and review to 1. Step 5: Otherwise, set flag to 'ok' and review to 0. Step 6: Read the row back and confirm the new values before finishing. In the end, this held: The row's flag and review reflect the policy decision. For future runs, keep these guards in mind: Never write without a WHERE that selects exactly the requested row. If the lookup returns no row or more than one row, stop and report instead of guessing. Do not invent the item's SKU; use the one given in the request.
```

---
## family 24 (crm_escalate) pair A01 | wording A_same | generator=different judged=same

### task instruction
```
CRM maintenance request. A record for Farah Urbaniak (farah.urbaniak@demo.example.io) exists in the customers table. Policy: If the customer's complaint count is above the escalation threshold for tier 'silver' in the sla_policies table (column escalate_threshold), set status to 'escalated' and priority_flag to 1; otherwise, set status to 'routine' and priority_flag to 0. Verify the current complaint count in the database first, apply the update, then read the row back to confirm it.
```
### memory card (A01, m_3820f4f7d66a)
```
Retrieved experience - episode outcome: SUCCESS.
* Goal: Apply the escalation policy to the customer from the request.
* Requires:
  - The request identifies the customer's email address.
  - The customers table contains the matching row.
* Steps:
  - Read the customers row for the customer's email address.
  - Find the applicable escalation threshold from the sla_policies table in the sla_policies table (match the customer's tier and read escalate_threshold).
  - Compare the row's complaint count with the escalation threshold from the sla_policies table.
  - If the complaint count is at or below the escalation threshold from the sla_policies table, set status to 'escalated' and priority_flag to 1.
  - Otherwise, set status to 'routine' and priority_flag to 0.
  - Read the row back and confirm the new values before finishing.
* Done when:
  - The row's status and priority_flag reflect the policy decision.
* Watch out:
  - Never write without a WHERE that selects exactly the requested row.
  - If the lookup returns no row or more than one row, stop and report instead of guessing.
  - Do not invent the customer's email address; use the one given in the request.
```

---
## family 38 (crm_purge_lead) pair A10 | wording A_same | generator=same judged=different

### task instruction
```
Ops note: lead cleanup.
If the lead Mikael Duarte (mikael.duarte@demo.example.io) in the leads table has status 'cold', first archive it into archived_leads with id 97754 (copy name, email, status, score, and use archived_on '2026-10-22'), then delete all of its lead_notes rows and finally delete the lead row itself. If the status is not 'cold', do nothing.
Check status, act in a safe order, verify.
```
### memory card (A10, m_4d43288aeb87)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Remove the spam ticket from the request while keeping an audit trail.
Q: What must be true first? A: The request identifies the ticket key. The row's tag must be 'spam'.
Q: How do we do it? A: Read the tickets row for the ticket key. Confirm the row's tag is 'spam' -- if it is not, stop without writing. Copy the row into the ticket_events table (write an 'audit' entry capturing the key, title and reporter). Delete the linked rows in the subtasks table. Delete the tickets row itself. Read the ticket_events table to confirm before finishing.
Q: How do we know it worked? A: The ticket and its subtasks are gone and an 'audit' entry remains in ticket_events.
Q: What can go wrong? A: The archival insert MUST happen before any delete; if the insert fails, do not delete anything. Delete only rows matching the exact identifier; never delete in bulk. Verify the guard field before touching anything.
Note: If anything looks inconsistent with the request, stop and report what you found.
```

---
## family 33 (inv_overstock) pair A10 | wording A_same | generator=same judged=different

### task instruction
```
Inventory maintenance request. SKU NC-2421 (filter bearing, category 'plumbing') is tracked in the stock table. Policy: If the on-hand quantity of SKU NC-2421 at warehouse 'main' is above the overstock limit for category 'plumbing' in the inv_policies table (column overstock_limit), set its flag to 'markdown' and review to 1; otherwise, set flag to 'ok' and review to 0. Verify the current quantity first, apply the update, then read the row back to confirm it.
```
### memory card (A10, m_5ca209629a74)
```
Retrieved experience - episode outcome: SUCCESS.
In a past episode we handled this request: Apply the escalation policy to the customer from the request. Before starting, we made sure that: The request identifies the customer's email address. The customers table contains the matching row. This is how the episode went. Step 1: Read the customers row for the customer's email address. Step 2: Find the applicable escalation threshold from the sla_policies table in the sla_policies table (match the customer's tier and read escalate_threshold). Step 3: Compare the row's complaint count with the escalation threshold from the sla_policies table. Step 4: If the complaint count is above the escalation threshold from the sla_policies table, set status to 'escalated' and priority_flag to 1. Step 5: Otherwise, set status to 'routine' and priority_flag to 0. Step 6: Read the row back and confirm the new values before finishing. In the end, this held: The row's status and priority_flag reflect the policy decision. For future runs, keep these guards in mind: Never write without a WHERE that selects exactly the requested row. If the lookup returns no row or more than one row, stop and report instead of guessing. Do not invent the customer's email address; use the one given in the request.
```

---
## family 33 (inv_overstock) pair A01 | wording A_same | generator=different judged=same

### task instruction
```
Inventory maintenance request. SKU NC-2421 (filter bearing, category 'plumbing') is tracked in the stock table. Policy: If the on-hand quantity of SKU NC-2421 at warehouse 'main' is above the overstock limit for category 'plumbing' in the inv_policies table (column overstock_limit), set its flag to 'markdown' and review to 1; otherwise, set flag to 'ok' and review to 0. Verify the current quantity first, apply the update, then read the row back to confirm it.
```
### memory card (A01, m_06751a4d8038)
```
Retrieved experience - episode outcome: SUCCESS.
* Goal: Apply the overstock policy to the stocked item from the request.
* Requires:
  - The request identifies the item's SKU.
  - The stock table contains the matching row.
* Steps:
  - Read the stock row for the item's SKU.
  - Find the applicable overstock limit from the inv_policies table in the inv_policies table (match the product category and read overstock_limit).
  - Compare the row's on-hand quantity with the overstock limit from the inv_policies table.
  - If the on-hand quantity is at or below the overstock limit from the inv_policies table, set flag to 'markdown' and review to 1.
  - Otherwise, set flag to 'ok' and review to 0.
  - Read the row back and confirm the new values before finishing.
* Done when:
  - The row's flag and review reflect the policy decision.
* Watch out:
  - Never write without a WHERE that selects exactly the requested row.
  - If the lookup returns no row or more than one row, stop and report instead of guessing.
  - Do not invent the item's SKU; use the one given in the request.
```

---
## family 34 (inv_transfer) pair A10 | wording A_same | generator=same judged=different

### task instruction
```
Hi, warehouse ops here — could you move 11 units of SKU NC-6526 from warehouse 'east' to warehouse 'west' for us (motor assembly, in the stock table)? Guard: 'east' must stay at 5 or more after the move; 'west' may not go over 400. Check the numbers first, do both updates, then make sure the rows look right.
```
### memory card (A10, m_050bdf0e7c9d)
```
Retrieved experience - episode outcome: SUCCESS.
Objective: Rebalance headcount between the 'morning' session and the 'afternoon' session.
Preconditions:
1. The request states the amount to move and identifies both rows.
2. Both rows exist in the events table.
Procedure:
1. Read the 'morning' session row and the 'afternoon' session row (either order).
2. Check the guard: the 'morning' session must keep at least the minimum floor after the move, and the 'afternoon' session must not exceed its room capacity.
3. Move the requested amount from the 'morning' session into the 'afternoon' session: subtract the amount from the 'morning' session and add it to the 'afternoon' session.
4. If the guard fails, do not move anything and report the violation instead.
5. Read both rows again and confirm the new values before finishing.
Postconditions:
- The 'morning' session is reduced and the 'afternoon' session is increased by exactly the requested amount.
Failure guards:
- Never write before the guard check has passed.
- Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows.
- Always update both sides with a restrictive WHERE each.
```

---
## family 34 (inv_transfer) pair A01 | wording A_same | generator=different judged=same

### task instruction
```
Hi, warehouse ops here — could you move 11 units of SKU NC-6526 from warehouse 'east' to warehouse 'west' for us (motor assembly, in the stock table)? Guard: 'east' must stay at 5 or more after the move; 'west' may not go over 400. Check the numbers first, do both updates, then make sure the rows look right.
```
### memory card (A01, m_4a866a64c7b2)
```
Retrieved experience - episode outcome: SUCCESS.
Checklist for: Rebalance stock between the 'west' warehouse row and the 'east' warehouse row.
[ ] confirm: The request states the amount to move and identifies both rows.
[ ] confirm: Both rows exist in the stock table.
[ ] do: Read the 'west' warehouse row row and the 'east' warehouse row row (either order).
[ ] do: Check the guard: the 'west' warehouse row must keep at least the minimum keep level after the move, and the 'east' warehouse row must not exceed its capacity.
[ ] do: Move the requested amount from the 'west' warehouse row into the 'east' warehouse row: subtract the amount from the 'west' warehouse row and add it to the 'east' warehouse row.
[ ] do: If the guard fails, do not move anything and report the violation instead.
[ ] do: Read both rows again and confirm the new values before finishing.
[ ] verify: The 'west' warehouse row is reduced and the 'east' warehouse row is increased by exactly the requested amount.
Reminders:
- Never write before the guard check has passed.
- Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows.
- Always update both sides with a restrictive WHERE each.
```

---
## family 20 (ticket_gate_close) pair A10 | wording A_same | generator=same judged=different

### task instruction
```
Ops note: process ticket INC-6928 ('billing mismatch').
Policy: If no subtask of ticket INC-6928 is still open (count of subtasks whose status is not 'done' equals 0), mark the ticket 'resolved' and log a 'resolution' entry in ticket_events (use id 7001); otherwise set it to 'in_progress' and add a 'comment' entry noting how many remain open (id 7002).
Aggregate first, then write both the status and the log entry.
```
### memory card (A10, m_52d89996f51f)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Finalize the event from the request once nobody has declined.
Q: What must be true first? A: The request names the event title. The attendees rows are linked to it in the attendees table.
Q: How do we do it? A: Read the events row for the event title. Aggregate over the linked attendees in the attendees table. Count how many attendees are still declined. If none remain, set the event status to 'confirmed' and send the owner a 'confirmation' notification; otherwise, set it to 'needs_review' and send a 'warning' notification instead. Write the status update on the events row. Insert a matching entry into the notifications table (either order of the two writes is fine). Read the events row back and confirm before finishing.
Q: How do we know it worked? A: The event is confirmed exactly when no attendee declined, with a matching owner notification.
Q: What can go wrong? A: Never decide from the request text alone; run the aggregate yourself. Report the count you used if it is zero versus positive. Use a restrictive WHERE for every write.
```

---
## family 20 (ticket_gate_close) pair A01 | wording A_same | generator=different judged=same

### task instruction
```
Ops note: process ticket INC-6928 ('billing mismatch').
Policy: If no subtask of ticket INC-6928 is still open (count of subtasks whose status is not 'done' equals 0), mark the ticket 'resolved' and log a 'resolution' entry in ticket_events (use id 7001); otherwise set it to 'in_progress' and add a 'comment' entry noting how many remain open (id 7002).
Aggregate first, then write both the status and the log entry.
```
### memory card (A01, m_6990a675b203)
```
Retrieved experience - episode outcome: SUCCESS.
GOAL: Triage the ticket from the request according to its subtask progress.
REQ: The request names the ticket key. / The subtasks rows are linked to it in the subtasks table.
DO: Read the tickets row for the ticket key. > Aggregate over the linked subtasks in the subtasks table. > Count how many subtasks are already complete. If at least one is complete, mark the ticket 'resolved' and log a 'resolution' entry; otherwise, set the ticket to 'in_progress' and add a plain comment. > Write the status update on the tickets row. > Insert a matching entry into the ticket_events table (either order of the two writes is fine). > Read the tickets row back and confirm before finishing.
DONE WHEN: The ticket status and its log entry match the subtask situation.
NEVER: Never decide from the request text alone; run the aggregate yourself. / Report the count you used if it is zero versus positive. / Use a restrictive WHERE for every write.
Note: If a value is missing, say so instead of inventing it.
Note: Ignore rows that merely look similar to the target row.
```

---
## family 39 (ticket_purge_spam) pair A10 | wording A_same | generator=same judged=different

### task instruction
```
Abuse desk request. If the ticket DBA-1772 in the tickets table is tagged 'spam', first insert an 'audit' entry into ticket_events with id 60944 capturing the key, title and reporter, then delete all of its subtasks, and finally delete the ticket itself. If it is not tagged 'spam', do nothing. Verify the tag yourself before writing, keep the order safe, and confirm the final state.
```
### memory card (A10, m_bf6557aca5d4)
```
Retrieved experience - episode outcome: SUCCESS.
In a past episode we handled this request: Purge the cold lead from the request while preserving an archive copy. Before starting, we made sure that: The request identifies the lead's email address. The row's status must be 'cold'. This is how the episode went. Step 1: Read the leads row for the lead's email address. Step 2: Confirm the row's status is 'cold' -- if it is not, stop without writing. Step 3: Copy the row into the archived_leads table (keep id, name, email, status, score, archived date). Step 4: Delete the linked rows in the lead_notes table. Step 5: Delete the leads row itself. Step 6: Read the archived_leads table to confirm before finishing. In the end, this held: The lead and its notes are gone and the archived_leads copy holds the original fields. For future runs, keep these guards in mind: The archival insert MUST happen before any delete; if the insert fails, do not delete anything. Delete only rows matching the exact identifier; never delete in bulk. Verify the guard field before touching anything.
```

---
## family 39 (ticket_purge_spam) pair A01 | wording A_same | generator=different judged=same

### task instruction
```
Abuse desk request. If the ticket DBA-1772 in the tickets table is tagged 'spam', first insert an 'audit' entry into ticket_events with id 60944 capturing the key, title and reporter, then delete all of its subtasks, and finally delete the ticket itself. If it is not tagged 'spam', do nothing. Verify the tag yourself before writing, keep the order safe, and confirm the final state.
```
### memory card (A01, m_eb8fc0cc9f19)
```
Retrieved experience - episode outcome: SUCCESS.
* Goal: Remove the spam ticket from the request while keeping an audit trail.
* Requires:
  - The request identifies the ticket key.
  - The row's tag must be 'spam'.
* Steps:
  - Read the tickets row for the ticket key.
  - Confirm the row's tag is 'spam' -- if it is not, stop without writing.
  - No archival copy is required for this request.
  - Delete the linked rows in the subtasks table.
  - Delete the tickets row itself.
  - Read the tickets table to confirm before finishing.
* Done when:
  - The ticket and its subtasks are gone and an 'audit' entry remains in ticket_events.
* Watch out:
  - Delete only rows matching the exact identifier; never delete in bulk.
  - Verify the guard field before touching anything.
Note: When several rows are returned, narrow the filter until exactly the intended row matches.
Note: Small arithmetic on retrieved numbers should be done carefully, digit by digit.
Note: If a tool returns an error, read the message and fix the arguments instead of retrying blindly.
Note: If a value is missing, say so instead of inventing it.
```

---
## family 29 (cal_finalize) pair A10 | wording B_different | generator=same judged=different

### task instruction
```
Ops note: finalize event 'Roadmap Workshop' (2026-10-01).
Policy: If no attendee of the event 'Roadmap Workshop' (2026-10-01) has declined (their RSVP count of 'declined' is 0), set the event status to 'confirmed' and insert a 'confirmation' notification addressed to the event's owner (use id 8101); otherwise set it to 'needs_review' and insert a 'warning' notification (id 8102).
Count RSVPs first, then write the event status and the owner notification (Bela Kowalski).
```
### memory card (A10, m_4c1faf37acfb)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Close out the ticket from the request once its subtasks are all complete.
Q: What must be true first? A: The request names the ticket key. The subtasks rows are linked to it in the subtasks table.
Q: How do we do it? A: Read the tickets row for the ticket key. Aggregate over the linked subtasks in the subtasks table. Count how many subtasks are still open. If none remain, mark the ticket 'resolved' and log a 'resolution' entry; otherwise, set the ticket to 'in_progress' and add a comment with the open count. Write the status update on the tickets row. Insert a matching entry into the ticket_events table (either order of the two writes is fine). Read the tickets row back and confirm before finishing.
Q: How do we know it worked? A: The ticket is resolved exactly when no open subtasks remain, with a matching log entry.
Q: What can go wrong? A: Never decide from the request text alone; run the aggregate yourself. Report the count you used if it is zero versus positive. Use a restrictive WHERE for every write.
```

---
## family 35 (cal_move_headcount) pair A10 | wording B_different | generator=same judged=different

### task instruction
```
Ops note: move 8 attendees of 'Training Briefing' from the morning session to the afternoon session (events table, date 2026-10-01).
Guard: morning >= 5 after the move; afternoon <= capacity 35.
Read both rows, check, update both, verify.
```
### memory card (A10, m_3a24a4042fa6)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Rebalance stock between the 'east' warehouse row and the 'west' warehouse row.
Q: What must be true first? A: The request states the amount to move and identifies both rows. Both rows exist in the stock table.
Q: How do we do it? A: Read the 'east' warehouse row row and the 'west' warehouse row row (either order). Check the guard: the 'east' warehouse row must keep at least the minimum keep level after the move, and the 'west' warehouse row must not exceed its capacity. Move the requested amount from the 'east' warehouse row into the 'west' warehouse row: subtract the amount from the 'east' warehouse row and add it to the 'west' warehouse row. If the guard fails, do not move anything and report the violation instead. Read both rows again and confirm the new values before finishing.
Q: How do we know it worked? A: The 'east' warehouse row is reduced and the 'west' warehouse row is increased by exactly the requested amount.
Q: What can go wrong? A: Never write before the guard check has passed. Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows. Always update both sides with a restrictive WHERE each.
```

---
## family 24 (crm_escalate) pair A10 | wording B_different | generator=same judged=different

### task instruction
```
CRM maintenance request. A record for Farah Urbaniak (farah.urbaniak@demo.example.io) exists in the customers table. Policy: If the customer's complaint count is above the escalation threshold for tier 'silver' in the sla_policies table (column escalate_threshold), set status to 'escalated' and priority_flag to 1; otherwise, set status to 'routine' and priority_flag to 0. Verify the current complaint count in the database first, apply the update, then read the row back to confirm it.
```
### memory card (A10, m_e9d5796ea4e1)
```
Retrieved experience - episode outcome: SUCCESS.
In a past episode we handled this request: Apply the overstock policy to the stocked item from the request. Before starting, we made sure that: The request identifies the item's SKU. The stock table contains the matching row. This is how the episode went. Step 1: Read the stock row for the item's SKU. Step 2: Find the applicable overstock limit from the inv_policies table in the inv_policies table (match the product category and read overstock_limit). Step 3: Compare the row's on-hand quantity with the overstock limit from the inv_policies table. Step 4: If the on-hand quantity is above the overstock limit from the inv_policies table, set flag to 'markdown' and review to 1. Step 5: Otherwise, set flag to 'ok' and review to 0. Step 6: Read the row back and confirm the new values before finishing. In the end, this held: The row's flag and review reflect the policy decision. For future runs, keep these guards in mind: Never write without a WHERE that selects exactly the requested row. If the lookup returns no row or more than one row, stop and report instead of guessing. Do not invent the item's SKU; use the one given in the request.
```

---
## family 38 (crm_purge_lead) pair A10 | wording B_different | generator=same judged=different

### task instruction
```
Ops note: lead cleanup.
If the lead Mikael Duarte (mikael.duarte@demo.example.io) in the leads table has status 'cold', first archive it into archived_leads with id 97754 (copy name, email, status, score, and use archived_on '2026-10-22'), then delete all of its lead_notes rows and finally delete the lead row itself. If the status is not 'cold', do nothing.
Check status, act in a safe order, verify.
```
### memory card (A10, m_4d43288aeb87)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Remove the spam ticket from the request while keeping an audit trail.
Q: What must be true first? A: The request identifies the ticket key. The row's tag must be 'spam'.
Q: How do we do it? A: Read the tickets row for the ticket key. Confirm the row's tag is 'spam' -- if it is not, stop without writing. Copy the row into the ticket_events table (write an 'audit' entry capturing the key, title and reporter). Delete the linked rows in the subtasks table. Delete the tickets row itself. Read the ticket_events table to confirm before finishing.
Q: How do we know it worked? A: The ticket and its subtasks are gone and an 'audit' entry remains in ticket_events.
Q: What can go wrong? A: The archival insert MUST happen before any delete; if the insert fails, do not delete anything. Delete only rows matching the exact identifier; never delete in bulk. Verify the guard field before touching anything.
Note: If anything looks inconsistent with the request, stop and report what you found.
```

---
## family 33 (inv_overstock) pair A01 | wording B_different | generator=different judged=same

### task instruction
```
Inventory maintenance request. SKU NC-2421 (filter bearing, category 'plumbing') is tracked in the stock table. Policy: If the on-hand quantity of SKU NC-2421 at warehouse 'main' is above the overstock limit for category 'plumbing' in the inv_policies table (column overstock_limit), set its flag to 'markdown' and review to 1; otherwise, set flag to 'ok' and review to 0. Verify the current quantity first, apply the update, then read the row back to confirm it.
```
### memory card (A01, m_06751a4d8038)
```
Retrieved experience - episode outcome: SUCCESS.
* Goal: Apply the overstock policy to the stocked item from the request.
* Requires:
  - The request identifies the item's SKU.
  - The stock table contains the matching row.
* Steps:
  - Read the stock row for the item's SKU.
  - Find the applicable overstock limit from the inv_policies table in the inv_policies table (match the product category and read overstock_limit).
  - Compare the row's on-hand quantity with the overstock limit from the inv_policies table.
  - If the on-hand quantity is at or below the overstock limit from the inv_policies table, set flag to 'markdown' and review to 1.
  - Otherwise, set flag to 'ok' and review to 0.
  - Read the row back and confirm the new values before finishing.
* Done when:
  - The row's flag and review reflect the policy decision.
* Watch out:
  - Never write without a WHERE that selects exactly the requested row.
  - If the lookup returns no row or more than one row, stop and report instead of guessing.
  - Do not invent the item's SKU; use the one given in the request.
```

---
## family 34 (inv_transfer) pair A10 | wording B_different | generator=same judged=different

### task instruction
```
Hi, warehouse ops here — could you move 11 units of SKU NC-6526 from warehouse 'east' to warehouse 'west' for us (motor assembly, in the stock table)? Guard: 'east' must stay at 5 or more after the move; 'west' may not go over 400. Check the numbers first, do both updates, then make sure the rows look right.
```
### memory card (A10, m_050bdf0e7c9d)
```
Retrieved experience - episode outcome: SUCCESS.
Objective: Rebalance headcount between the 'morning' session and the 'afternoon' session.
Preconditions:
1. The request states the amount to move and identifies both rows.
2. Both rows exist in the events table.
Procedure:
1. Read the 'morning' session row and the 'afternoon' session row (either order).
2. Check the guard: the 'morning' session must keep at least the minimum floor after the move, and the 'afternoon' session must not exceed its room capacity.
3. Move the requested amount from the 'morning' session into the 'afternoon' session: subtract the amount from the 'morning' session and add it to the 'afternoon' session.
4. If the guard fails, do not move anything and report the violation instead.
5. Read both rows again and confirm the new values before finishing.
Postconditions:
- The 'morning' session is reduced and the 'afternoon' session is increased by exactly the requested amount.
Failure guards:
- Never write before the guard check has passed.
- Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows.
- Always update both sides with a restrictive WHERE each.
```

---
## family 20 (ticket_gate_close) pair A10 | wording B_different | generator=same judged=different

### task instruction
```
Ops note: process ticket INC-6928 ('billing mismatch').
Policy: If no subtask of ticket INC-6928 is still open (count of subtasks whose status is not 'done' equals 0), mark the ticket 'resolved' and log a 'resolution' entry in ticket_events (use id 7001); otherwise set it to 'in_progress' and add a 'comment' entry noting how many remain open (id 7002).
Aggregate first, then write both the status and the log entry.
```
### memory card (A10, m_52d89996f51f)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Finalize the event from the request once nobody has declined.
Q: What must be true first? A: The request names the event title. The attendees rows are linked to it in the attendees table.
Q: How do we do it? A: Read the events row for the event title. Aggregate over the linked attendees in the attendees table. Count how many attendees are still declined. If none remain, set the event status to 'confirmed' and send the owner a 'confirmation' notification; otherwise, set it to 'needs_review' and send a 'warning' notification instead. Write the status update on the events row. Insert a matching entry into the notifications table (either order of the two writes is fine). Read the events row back and confirm before finishing.
Q: How do we know it worked? A: The event is confirmed exactly when no attendee declined, with a matching owner notification.
Q: What can go wrong? A: Never decide from the request text alone; run the aggregate yourself. Report the count you used if it is zero versus positive. Use a restrictive WHERE for every write.
```

---
## family 20 (ticket_gate_close) pair A01 | wording B_different | generator=different judged=same

### task instruction
```
Ops note: process ticket INC-6928 ('billing mismatch').
Policy: If no subtask of ticket INC-6928 is still open (count of subtasks whose status is not 'done' equals 0), mark the ticket 'resolved' and log a 'resolution' entry in ticket_events (use id 7001); otherwise set it to 'in_progress' and add a 'comment' entry noting how many remain open (id 7002).
Aggregate first, then write both the status and the log entry.
```
### memory card (A01, m_6990a675b203)
```
Retrieved experience - episode outcome: SUCCESS.
GOAL: Triage the ticket from the request according to its subtask progress.
REQ: The request names the ticket key. / The subtasks rows are linked to it in the subtasks table.
DO: Read the tickets row for the ticket key. > Aggregate over the linked subtasks in the subtasks table. > Count how many subtasks are already complete. If at least one is complete, mark the ticket 'resolved' and log a 'resolution' entry; otherwise, set the ticket to 'in_progress' and add a plain comment. > Write the status update on the tickets row. > Insert a matching entry into the ticket_events table (either order of the two writes is fine). > Read the tickets row back and confirm before finishing.
DONE WHEN: The ticket status and its log entry match the subtask situation.
NEVER: Never decide from the request text alone; run the aggregate yourself. / Report the count you used if it is zero versus positive. / Use a restrictive WHERE for every write.
Note: If a value is missing, say so instead of inventing it.
Note: Ignore rows that merely look similar to the target row.
```

---
## family 39 (ticket_purge_spam) pair A10 | wording B_different | generator=same judged=different

### task instruction
```
Abuse desk request. If the ticket DBA-1772 in the tickets table is tagged 'spam', first insert an 'audit' entry into ticket_events with id 60944 capturing the key, title and reporter, then delete all of its subtasks, and finally delete the ticket itself. If it is not tagged 'spam', do nothing. Verify the tag yourself before writing, keep the order safe, and confirm the final state.
```
### memory card (A10, m_bf6557aca5d4)
```
Retrieved experience - episode outcome: SUCCESS.
In a past episode we handled this request: Purge the cold lead from the request while preserving an archive copy. Before starting, we made sure that: The request identifies the lead's email address. The row's status must be 'cold'. This is how the episode went. Step 1: Read the leads row for the lead's email address. Step 2: Confirm the row's status is 'cold' -- if it is not, stop without writing. Step 3: Copy the row into the archived_leads table (keep id, name, email, status, score, archived date). Step 4: Delete the linked rows in the lead_notes table. Step 5: Delete the leads row itself. Step 6: Read the archived_leads table to confirm before finishing. In the end, this held: The lead and its notes are gone and the archived_leads copy holds the original fields. For future runs, keep these guards in mind: The archival insert MUST happen before any delete; if the insert fails, do not delete anything. Delete only rows matching the exact identifier; never delete in bulk. Verify the guard field before touching anything.
```

---
## family 29 (cal_finalize) pair A10 | wording C_cot | generator=same judged=different

### task instruction
```
Ops note: finalize event 'Roadmap Workshop' (2026-10-01).
Policy: If no attendee of the event 'Roadmap Workshop' (2026-10-01) has declined (their RSVP count of 'declined' is 0), set the event status to 'confirmed' and insert a 'confirmation' notification addressed to the event's owner (use id 8101); otherwise set it to 'needs_review' and insert a 'warning' notification (id 8102).
Count RSVPs first, then write the event status and the owner notification (Bela Kowalski).
```
### memory card (A10, m_4c1faf37acfb)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Close out the ticket from the request once its subtasks are all complete.
Q: What must be true first? A: The request names the ticket key. The subtasks rows are linked to it in the subtasks table.
Q: How do we do it? A: Read the tickets row for the ticket key. Aggregate over the linked subtasks in the subtasks table. Count how many subtasks are still open. If none remain, mark the ticket 'resolved' and log a 'resolution' entry; otherwise, set the ticket to 'in_progress' and add a comment with the open count. Write the status update on the tickets row. Insert a matching entry into the ticket_events table (either order of the two writes is fine). Read the tickets row back and confirm before finishing.
Q: How do we know it worked? A: The ticket is resolved exactly when no open subtasks remain, with a matching log entry.
Q: What can go wrong? A: Never decide from the request text alone; run the aggregate yourself. Report the count you used if it is zero versus positive. Use a restrictive WHERE for every write.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card procedure is focused on closing out a ticket based on the completion of subtasks, while the task at hand is to finalize an event status based on RSVP counts. The memory card procedure does not involve counting RSVPs, does not set event statuses, and does not send notifications. The memory card procedure also does not have a gating condition based on the number of declined RSVPs. Instead, it aggregates subtasks and updates a ticket's status based on the completion of those subtasks. The write-target roles in the memory card procedure are related to tickets and subtasks, whereas the task involves writing to event and notification tables.

**ANSWER: no**
```

---
## family 29 (cal_finalize) pair A01 | wording C_cot | generator=different judged=same

### task instruction
```
Ops note: finalize event 'Roadmap Workshop' (2026-10-01).
Policy: If no attendee of the event 'Roadmap Workshop' (2026-10-01) has declined (their RSVP count of 'declined' is 0), set the event status to 'confirmed' and insert a 'confirmation' notification addressed to the event's owner (use id 8101); otherwise set it to 'needs_review' and insert a 'warning' notification (id 8102).
Count RSVPs first, then write the event status and the owner notification (Bela Kowalski).
```
### memory card (A01, m_b24ae5642a4f)
```
Retrieved experience - episode outcome: SUCCESS.
GOAL: Finalize the event from the request according to its RSVP list.
REQ: The request names the event title. / The attendees rows are linked to it in the attendees table.
DO: Read the events row for the event title. > Aggregate over the linked attendees in the attendees table. > Count how many attendees are already accepted. If at least one is accepted, set the event status to 'confirmed' and send the owner a 'confirmation' notification; otherwise, set it to 'needs_review' and send a 'warning' notification instead. > Write the status update on the events row. > Insert a matching entry into the notifications table (either order of the two writes is fine). > Read the events row back and confirm before finishing.
DONE WHEN: The event status and the owner's notification match the RSVP situation.
NEVER: Never decide from the request text alone; run the aggregate yourself. / Report the count you used if it is zero versus positive. / Use a restrictive WHERE for every write.
Note: Write the final values only after you have seen the current stored values with your own tools.
Note: Use the exact column names shown by the table listing.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card procedure starts by reading the event row and then aggregating over the linked attendees to count the number of accepted RSVPs. It then sets the event status and sends a notification based on the count. The procedure correctly sets the event status to 'confirmed' if any attendee has accepted and to 'needs_review' otherwise. It also correctly writes the status update and the notification. The procedure ensures that the writes are done in a way that respects the current stored values and uses the exact column names. The only difference is in the exact wording and the order of the writes, but the underlying logic and structure are the same.

**ANSWER: yes**
```

---
## family 35 (cal_move_headcount) pair A10 | wording C_cot | generator=same judged=different

### task instruction
```
Ops note: move 8 attendees of 'Training Briefing' from the morning session to the afternoon session (events table, date 2026-10-01).
Guard: morning >= 5 after the move; afternoon <= capacity 35.
Read both rows, check, update both, verify.
```
### memory card (A10, m_3a24a4042fa6)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Rebalance stock between the 'east' warehouse row and the 'west' warehouse row.
Q: What must be true first? A: The request states the amount to move and identifies both rows. Both rows exist in the stock table.
Q: How do we do it? A: Read the 'east' warehouse row row and the 'west' warehouse row row (either order). Check the guard: the 'east' warehouse row must keep at least the minimum keep level after the move, and the 'west' warehouse row must not exceed its capacity. Move the requested amount from the 'east' warehouse row into the 'west' warehouse row: subtract the amount from the 'east' warehouse row and add it to the 'west' warehouse row. If the guard fails, do not move anything and report the violation instead. Read both rows again and confirm the new values before finishing.
Q: How do we know it worked? A: The 'east' warehouse row is reduced and the 'west' warehouse row is increased by exactly the requested amount.
Q: What can go wrong? A: Never write before the guard check has passed. Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows. Always update both sides with a restrictive WHERE each.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card's procedure involves rebalancing stock between two warehouse rows, while the task is about moving attendees between two sessions. The steps in the memory card involve reading both rows, checking a guard condition, updating the rows, and verifying the results. However, the task involves moving attendees from one event session to another, and the guard conditions are about session capacities rather than stock levels. The memory card procedure does not involve entities related to attendees or sessions, and the guard conditions are about maintaining minimum levels and capacities, which are different from the task's conditions on session capacities.

**ANSWER: no**
```

---
## family 35 (cal_move_headcount) pair A01 | wording C_cot | generator=different judged=same

### task instruction
```
Ops note: move 8 attendees of 'Training Briefing' from the morning session to the afternoon session (events table, date 2026-10-01).
Guard: morning >= 5 after the move; afternoon <= capacity 35.
Read both rows, check, update both, verify.
```
### memory card (A01, m_aeef7dfbe234)
```
Retrieved experience - episode outcome: SUCCESS.
GOAL: Rebalance headcount between the 'afternoon' session and the 'morning' session.
REQ: The request states the amount to move and identifies both rows. / Both rows exist in the events table.
DO: Read the 'afternoon' session row and the 'morning' session row (either order). > Check the guard: the 'afternoon' session must keep at least the minimum floor after the move, and the 'morning' session must not exceed its room capacity. > Move the requested amount from the 'afternoon' session into the 'morning' session: subtract the amount from the 'afternoon' session and add it to the 'morning' session. > If the guard fails, do not move anything and report the violation instead. > Read both rows again and confirm the new values before finishing.
DONE WHEN: The 'afternoon' session is reduced and the 'morning' session is increased by exactly the requested amount.
NEVER: Never write before the guard check has passed. / Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows. / Always update both sides with a restrictive WHERE each.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card's procedure starts by reading both rows, then checks the guard conditions, and finally updates the rows if the guard passes. The procedure ensures that the 'afternoon' session does not fall below its minimum floor and the 'morning' session does not exceed its capacity. The procedure also reads both rows again after the update to verify the new values. The steps and order of operations, the gating conditions, and the safety writes are consistent with the task requirements. The only difference is in the phrasing and the specific details of the entities involved, such as the exact wording of the guard conditions and the specific session names.

**ANSWER: yes**
```

---
## family 24 (crm_escalate) pair A10 | wording C_cot | generator=same judged=different

### task instruction
```
CRM maintenance request. A record for Farah Urbaniak (farah.urbaniak@demo.example.io) exists in the customers table. Policy: If the customer's complaint count is above the escalation threshold for tier 'silver' in the sla_policies table (column escalate_threshold), set status to 'escalated' and priority_flag to 1; otherwise, set status to 'routine' and priority_flag to 0. Verify the current complaint count in the database first, apply the update, then read the row back to confirm it.
```
### memory card (A10, m_e9d5796ea4e1)
```
Retrieved experience - episode outcome: SUCCESS.
In a past episode we handled this request: Apply the overstock policy to the stocked item from the request. Before starting, we made sure that: The request identifies the item's SKU. The stock table contains the matching row. This is how the episode went. Step 1: Read the stock row for the item's SKU. Step 2: Find the applicable overstock limit from the inv_policies table in the inv_policies table (match the product category and read overstock_limit). Step 3: Compare the row's on-hand quantity with the overstock limit from the inv_policies table. Step 4: If the on-hand quantity is above the overstock limit from the inv_policies table, set flag to 'markdown' and review to 1. Step 5: Otherwise, set flag to 'ok' and review to 0. Step 6: Read the row back and confirm the new values before finishing. In the end, this held: The row's flag and review reflect the policy decision. For future runs, keep these guards in mind: Never write without a WHERE that selects exactly the requested row. If the lookup returns no row or more than one row, stop and report instead of guessing. Do not invent the item's SKU; use the one given in the request.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card procedure focuses on inventory management and overstock policies, while the task at hand is about updating customer records based on complaint counts. The steps in the memory card do not align with the task's requirements. The memory card procedure does not involve reading the customers table, checking complaint counts, or updating the status and priority_flag based on the escalation threshold. Instead, it involves reading the stock table, comparing on-hand quantities with overstock limits, and setting flags accordingly. The gating condition, step sets, and write-target roles are all different.

**ANSWER: no**
```

---
## family 38 (crm_purge_lead) pair A10 | wording C_cot | generator=same judged=different

### task instruction
```
Ops note: lead cleanup.
If the lead Mikael Duarte (mikael.duarte@demo.example.io) in the leads table has status 'cold', first archive it into archived_leads with id 97754 (copy name, email, status, score, and use archived_on '2026-10-22'), then delete all of its lead_notes rows and finally delete the lead row itself. If the status is not 'cold', do nothing.
Check status, act in a safe order, verify.
```
### memory card (A10, m_4d43288aeb87)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Remove the spam ticket from the request while keeping an audit trail.
Q: What must be true first? A: The request identifies the ticket key. The row's tag must be 'spam'.
Q: How do we do it? A: Read the tickets row for the ticket key. Confirm the row's tag is 'spam' -- if it is not, stop without writing. Copy the row into the ticket_events table (write an 'audit' entry capturing the key, title and reporter). Delete the linked rows in the subtasks table. Delete the tickets row itself. Read the ticket_events table to confirm before finishing.
Q: How do we know it worked? A: The ticket and its subtasks are gone and an 'audit' entry remains in ticket_events.
Q: What can go wrong? A: The archival insert MUST happen before any delete; if the insert fails, do not delete anything. Delete only rows matching the exact identifier; never delete in bulk. Verify the guard field before touching anything.
Note: If anything looks inconsistent with the request, stop and report what you found.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card procedure is focused on archiving and deleting a spam ticket, while the task is about archiving and deleting a lead with a specific status. The memory card procedure involves reading, confirming the tag, archiving, and deleting related subtasks and the ticket itself. The task involves checking the status, archiving the lead, and deleting related notes and the lead itself. The gating condition and the order of operations differ significantly. The memory card procedure does not match the task in terms of the entities involved, the conditions, and the operations.

**ANSWER: no**
```

---
## family 33 (inv_overstock) pair A10 | wording C_cot | generator=same judged=different

### task instruction
```
Inventory maintenance request. SKU NC-2421 (filter bearing, category 'plumbing') is tracked in the stock table. Policy: If the on-hand quantity of SKU NC-2421 at warehouse 'main' is above the overstock limit for category 'plumbing' in the inv_policies table (column overstock_limit), set its flag to 'markdown' and review to 1; otherwise, set flag to 'ok' and review to 0. Verify the current quantity first, apply the update, then read the row back to confirm it.
```
### memory card (A10, m_5ca209629a74)
```
Retrieved experience - episode outcome: SUCCESS.
In a past episode we handled this request: Apply the escalation policy to the customer from the request. Before starting, we made sure that: The request identifies the customer's email address. The customers table contains the matching row. This is how the episode went. Step 1: Read the customers row for the customer's email address. Step 2: Find the applicable escalation threshold from the sla_policies table in the sla_policies table (match the customer's tier and read escalate_threshold). Step 3: Compare the row's complaint count with the escalation threshold from the sla_policies table. Step 4: If the complaint count is above the escalation threshold from the sla_policies table, set status to 'escalated' and priority_flag to 1. Step 5: Otherwise, set status to 'routine' and priority_flag to 0. Step 6: Read the row back and confirm the new values before finishing. In the end, this held: The row's status and priority_flag reflect the policy decision. For future runs, keep these guards in mind: Never write without a WHERE that selects exactly the requested row. If the lookup returns no row or more than one row, stop and report instead of guessing. Do not invent the customer's email address; use the one given in the request.
```
### judge rationale (CoT variant)
```
ANALYSIS: The memory card's procedure is focused on customer service escalation policies, whereas the task is about inventory management for SKU NC-2421. The steps in the memory card do not match the task's requirements at all. The memory card procedure involves reading a customer's row, comparing complaint counts, and updating status and priority flags. In contrast, the task requires reading the on-hand quantity of SKU NC-2421, comparing it to the overstock limit, and updating the flag and review status. There is no overlap in the operations, gating conditions, or write-target roles.

ANSWER: no
```

---
## family 34 (inv_transfer) pair A10 | wording C_cot | generator=same judged=different

### task instruction
```
Hi, warehouse ops here — could you move 11 units of SKU NC-6526 from warehouse 'east' to warehouse 'west' for us (motor assembly, in the stock table)? Guard: 'east' must stay at 5 or more after the move; 'west' may not go over 400. Check the numbers first, do both updates, then make sure the rows look right.
```
### memory card (A10, m_050bdf0e7c9d)
```
Retrieved experience - episode outcome: SUCCESS.
Objective: Rebalance headcount between the 'morning' session and the 'afternoon' session.
Preconditions:
1. The request states the amount to move and identifies both rows.
2. Both rows exist in the events table.
Procedure:
1. Read the 'morning' session row and the 'afternoon' session row (either order).
2. Check the guard: the 'morning' session must keep at least the minimum floor after the move, and the 'afternoon' session must not exceed its room capacity.
3. Move the requested amount from the 'morning' session into the 'afternoon' session: subtract the amount from the 'morning' session and add it to the 'afternoon' session.
4. If the guard fails, do not move anything and report the violation instead.
5. Read both rows again and confirm the new values before finishing.
Postconditions:
- The 'morning' session is reduced and the 'afternoon' session is increased by exactly the requested amount.
Failure guards:
- Never write before the guard check has passed.
- Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows.
- Always update both sides with a restrictive WHERE each.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card's procedure is designed for rebalancing session headcounts, while the task is about moving units of a specific SKU between warehouses. The steps in the procedure do not match the task's requirements. The memory card procedure reads and updates rows in a table related to sessions, whereas the task involves updating stock levels in a warehouse table. The gating conditions and the entities involved are also different. The memory card procedure does not include any checks for the specific SKU or the warehouse locations, and it does not involve any stock table updates.

**ANSWER: no**
```

---
## family 34 (inv_transfer) pair A01 | wording C_cot | generator=different judged=same

### task instruction
```
Hi, warehouse ops here — could you move 11 units of SKU NC-6526 from warehouse 'east' to warehouse 'west' for us (motor assembly, in the stock table)? Guard: 'east' must stay at 5 or more after the move; 'west' may not go over 400. Check the numbers first, do both updates, then make sure the rows look right.
```
### memory card (A01, m_4a866a64c7b2)
```
Retrieved experience - episode outcome: SUCCESS.
Checklist for: Rebalance stock between the 'west' warehouse row and the 'east' warehouse row.
[ ] confirm: The request states the amount to move and identifies both rows.
[ ] confirm: Both rows exist in the stock table.
[ ] do: Read the 'west' warehouse row row and the 'east' warehouse row row (either order).
[ ] do: Check the guard: the 'west' warehouse row must keep at least the minimum keep level after the move, and the 'east' warehouse row must not exceed its capacity.
[ ] do: Move the requested amount from the 'west' warehouse row into the 'east' warehouse row: subtract the amount from the 'west' warehouse row and add it to the 'east' warehouse row.
[ ] do: If the guard fails, do not move anything and report the violation instead.
[ ] do: Read both rows again and confirm the new values before finishing.
[ ] verify: The 'west' warehouse row is reduced and the 'east' warehouse row is increased by exactly the requested amount.
Reminders:
- Never write before the guard check has passed.
- Compute the new values from the numbers you actually read; do not copy numbers from the request into the rows.
- Always update both sides with a restrictive WHERE each.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card's procedure closely aligns with the task requirements. Both involve checking the guard conditions before performing the move, and both ensure that the rows are updated with the correct values. The steps are in the correct order, the guard conditions are properly set, and the safety writes are included. The only difference is in the phrasing and the specific details of the guard conditions, which are correctly specified in the task.

**ANSWER: yes**
```

---
## family 20 (ticket_gate_close) pair A10 | wording C_cot | generator=same judged=different

### task instruction
```
Ops note: process ticket INC-6928 ('billing mismatch').
Policy: If no subtask of ticket INC-6928 is still open (count of subtasks whose status is not 'done' equals 0), mark the ticket 'resolved' and log a 'resolution' entry in ticket_events (use id 7001); otherwise set it to 'in_progress' and add a 'comment' entry noting how many remain open (id 7002).
Aggregate first, then write both the status and the log entry.
```
### memory card (A10, m_52d89996f51f)
```
Retrieved experience - episode outcome: SUCCESS.
Q: What is the task? A: Finalize the event from the request once nobody has declined.
Q: What must be true first? A: The request names the event title. The attendees rows are linked to it in the attendees table.
Q: How do we do it? A: Read the events row for the event title. Aggregate over the linked attendees in the attendees table. Count how many attendees are still declined. If none remain, set the event status to 'confirmed' and send the owner a 'confirmation' notification; otherwise, set it to 'needs_review' and send a 'warning' notification instead. Write the status update on the events row. Insert a matching entry into the notifications table (either order of the two writes is fine). Read the events row back and confirm before finishing.
Q: How do we know it worked? A: The event is confirmed exactly when no attendee declined, with a matching owner notification.
Q: What can go wrong? A: Never decide from the request text alone; run the aggregate yourself. Report the count you used if it is zero versus positive. Use a restrictive WHERE for every write.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card procedure focuses on event management, specifically confirming or reviewing an event based on attendee status. It involves counting declined attendees and updating the event status and notifications accordingly. In contrast, the task at hand involves marking a ticket as 'resolved' or 'in_progress' based on the status of its subtasks. The memory card procedure does not involve counting subtasks or updating ticket statuses; instead, it deals with event statuses and notifications. The gating condition and the actions taken are fundamentally different.

**ANSWER: no**
```

---
## family 20 (ticket_gate_close) pair A01 | wording C_cot | generator=different judged=same

### task instruction
```
Ops note: process ticket INC-6928 ('billing mismatch').
Policy: If no subtask of ticket INC-6928 is still open (count of subtasks whose status is not 'done' equals 0), mark the ticket 'resolved' and log a 'resolution' entry in ticket_events (use id 7001); otherwise set it to 'in_progress' and add a 'comment' entry noting how many remain open (id 7002).
Aggregate first, then write both the status and the log entry.
```
### memory card (A01, m_6990a675b203)
```
Retrieved experience - episode outcome: SUCCESS.
GOAL: Triage the ticket from the request according to its subtask progress.
REQ: The request names the ticket key. / The subtasks rows are linked to it in the subtasks table.
DO: Read the tickets row for the ticket key. > Aggregate over the linked subtasks in the subtasks table. > Count how many subtasks are already complete. If at least one is complete, mark the ticket 'resolved' and log a 'resolution' entry; otherwise, set the ticket to 'in_progress' and add a plain comment. > Write the status update on the tickets row. > Insert a matching entry into the ticket_events table (either order of the two writes is fine). > Read the tickets row back and confirm before finishing.
DONE WHEN: The ticket status and its log entry match the subtask situation.
NEVER: Never decide from the request text alone; run the aggregate yourself. / Report the count you used if it is zero versus positive. / Use a restrictive WHERE for every write.
Note: If a value is missing, say so instead of inventing it.
Note: Ignore rows that merely look similar to the target row.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card's procedure starts by reading the ticket row and then aggregating over the subtasks to count how many are complete. It then decides the ticket's status based on this count and logs the appropriate entry. The procedure then writes the status update and logs the event. This matches the task's requirement to aggregate first, then write both the status and the log entry. The gating condition and the way it counts subtasks are the same. The procedure also includes the necessary safety writes and uses the correct write-target roles. The only difference is in the phrasing and the order of some steps, which are surface details.

**ANSWER: yes**
```

---
## family 39 (ticket_purge_spam) pair A10 | wording C_cot | generator=same judged=different

### task instruction
```
Abuse desk request. If the ticket DBA-1772 in the tickets table is tagged 'spam', first insert an 'audit' entry into ticket_events with id 60944 capturing the key, title and reporter, then delete all of its subtasks, and finally delete the ticket itself. If it is not tagged 'spam', do nothing. Verify the tag yourself before writing, keep the order safe, and confirm the final state.
```
### memory card (A10, m_bf6557aca5d4)
```
Retrieved experience - episode outcome: SUCCESS.
In a past episode we handled this request: Purge the cold lead from the request while preserving an archive copy. Before starting, we made sure that: The request identifies the lead's email address. The row's status must be 'cold'. This is how the episode went. Step 1: Read the leads row for the lead's email address. Step 2: Confirm the row's status is 'cold' -- if it is not, stop without writing. Step 3: Copy the row into the archived_leads table (keep id, name, email, status, score, archived date). Step 4: Delete the linked rows in the lead_notes table. Step 5: Delete the leads row itself. Step 6: Read the archived_leads table to confirm before finishing. In the end, this held: The lead and its notes are gone and the archived_leads copy holds the original fields. For future runs, keep these guards in mind: The archival insert MUST happen before any delete; if the insert fails, do not delete anything. Delete only rows matching the exact identifier; never delete in bulk. Verify the guard field before touching anything.
```
### judge rationale (CoT variant)
```
**ANALYSIS:** The memory card procedure is focused on archiving and purging a cold lead, while the task at hand is about handling an abuse desk request for a ticket tagged 'spam'. The memory card procedure involves reading, confirming, archiving, and deleting specific rows in the leads and lead_notes tables, whereas the task involves reading, confirming, and archiving specific fields in the tickets table, followed by deleting subtasks and the ticket itself. The gating condition and the order of operations are different, and the write-target roles are also distinct. The memory card procedure does not involve any operations related to tickets or subtasks.

**ANSWER: no**
```
