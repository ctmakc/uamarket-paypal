# Locker pickup: the owner's decisions

Moved out of `docs/OWNER-ACTIONS.md` on 17.09.2026: the shop opens with shipping only, and
none of this blocks opening. Pickup stays off at checkout, and every page says so, until
`PICKUP_ADDRESS` is set. Client addresses for the per-address lockouts below come from Caddy
through the storefront (`INTERNAL_PROXY_SECRET`, see `docs/LAUNCH-RUNBOOK.md`), so there is
no proxy list to maintain.

## 1. The locker in the courier's hands

- **How many wrong PIN entries should shut a courier pickup out?** Default: 5 wrong entries
  inside 15 minutes, after which that pickup is refused for 15 minutes. A courier who
  fat-fingers the keypad four times still gets in on the fifth try. Change with
  `COURIER_PIN_MAX_FAILURES`, `COURIER_PIN_FAILURE_WINDOW_SECONDS` and
  `COURIER_PIN_LOCKOUT_SECONDS`.
- **How many wrong PIN entries from one internet address should be shut out?** Default: 15
  failures inside 15 minutes across all pickups, then that address is refused for 15 minutes.
  This is what stops somebody working through pickup after pickup. Change with
  `COURIER_PIN_IP_MAX_FAILURES` and `COURIER_PIN_IP_LOCKOUT_SECONDS`.
- **Is a 6-digit PIN long enough?** With the blocking above, guessing one PIN takes far
  longer than any pickup window, so 6 digits holds. If couriers will share PINs by phone, or
  the window is ever widened to a whole day, say so and the PIN gets longer.
- **Who may unlock a pickup that got shut out, and does it need a new PIN?** Right now any
  operator key can call `POST /v1/pickups/{pickup_id}/access/unlock`, which reopens PIN entry
  and closes the alert on the dashboard. The old PIN keeps working. Decide whether an unlock
  should also force a new pickup with a new PIN — if a stranger was guessing, the PIN may be
  known to them.
- **Who is allowed to force a locker bay shut, and how does it come back?** An operator can
  push `inner_gate_closed` or `outer_door_closed` to false through
  `POST /v1/bays/{bay_id}/state`. That takes the bay out of service and writes a
  `BAY_MANUAL_HOLD` alert. Nobody can push those fields back to true from the office — only
  the locker's own controller reports a gate or door as closed. Confirm that a technician
  standing at the locker is the intended way to clear a hold.
- **Where does the operator see these alerts?** Both `COURIER_PIN_LOCKOUT` and
  `BAY_MANUAL_HOLD` land in the exception list on the dashboard. Confirm whether a locked-out
  pickup should also raise a phone or email alert; nothing is sent today.
- **How many times may the office computer offer the same locker command before it gives
  up?** Default: 5 offers, with a growing pause between them (5 seconds, then 10, then 15…).
  After the fifth the command is parked, an `EDGE_COMMAND_ABANDONED` alert is written, and the
  courier needs a fresh pickup. Before this, the office repeated every unhandled command about
  once a second for as long as the controller stayed connected. Change with
  `EDGE_COMMAND_MAX_ATTEMPTS` and `EDGE_COMMAND_RETRY_BACKOFF_SECONDS`.
- **An unlock whose time window has passed is thrown away instead of sent.** The command is
  parked with an `EDGE_COMMAND_EXPIRED` alert. This is what stops a bay opening hours later,
  after the courier has gone, because the controller was offline at the time. Confirm this is
  what you want, and say who watches those alerts.
- **Should a bay go out of service when the controller cannot prove the unlock coil switched
  off again?** Default: yes. The bay is disabled, a `LOCKER_COIL_LATCHED` alert is written,
  and nothing can be assigned to that bay until somebody re-enables it. A latch that may still
  be held open is a physical problem. Turn the automatic disable off with
  `EDGE_DISABLE_BAY_ON_COIL_FAULT=false` to decide case by case — then name who goes to the
  garage.
- **Who re-enables a bay after a latched-coil alert, and what do they check first?** Nothing
  in the software re-enables it. Write down the check (coil de-energized at the panel, door
  re-locked, lock feedback reading locked) and who signs it off.
- **How many times should the controller try to switch the unlock coil off before calling it
  a fault?** Default: 3 attempts, 100 milliseconds apart, each one confirmed by reading the
  coil back from the controller. Change with `LOCKER_UNLOCK_RELEASE_ATTEMPTS` and
  `LOCKER_UNLOCK_RELEASE_RETRY_MS`.
- **A command interrupted in the middle of driving the latch is never repeated
  automatically.** The controller reports it as indeterminate and refuses to pulse again,
  because nothing in the software can tell whether the door already opened. The courier then
  needs a new pickup with a new PIN. Confirm this, and name who tells the courier at the door.
- **Which bays does each garage controller own?** Until you say, the office works it out from
  where it sends that bay's commands, and a bay nobody has been commanded about can be
  reported by any provisioned controller at the site. With one controller in one garage that
  is correct. Before a second controller or a second site is added, list the bays for each one
  in `EDGE_BAY_OWNERS_JSON`, for example
  `{"garage-ottawa-01/LOCKER-PLC-01": ["BAY-CP", "BAY-OTHER"]}`.
- **How quickly must a revoked or rotated controller token kill a connection that is already
  open?** Default: within 5 seconds — the open connection re-checks its credential on that
  schedule and hangs up as soon as it stops being valid. Change with
  `EDGE_CREDENTIAL_RECHECK_SECONDS`. Shorter is safer and costs one small database read per
  connection per interval.

## 2. The locker in the buyer's hands

Section 1 is the locker as the courier meets it. This section is the same box seen by a
customer who chose "collect it from the locker" at the checkout: what the shop has to know
before it may sell that method, and what the buyer is told once their parcel is inside.

- **Where is the locker?** Default: nothing, and there is no default to fall back on —
  `PICKUP_ADDRESS` is empty and the software has no way of guessing a street address. While
  it is empty the checkout stops offering pickup altogether: the method disappears from the
  page, an order that asks for it anyway is refused, and the FAQ and the shipping page fall
  back to their "pickup is switched off" wording. Send the address a person can walk to —
  street, number, city, postal code — and pickup appears the moment it is typed in. This is
  the one answer the whole section waits on. There is a second setting for the same address,
  `SHOP_PICKUP_ADDRESS_JSON`, because Google is handed it field by field. Filling in either
  one is enough, and filling in both is safe: the structured one wins everywhere, so the
  street a page prints and the street Google reads are always the same. Use the plain
  `PICKUP_ADDRESS` on its own if you would rather write one line and skip the fields.
- **When can somebody come?** Default: nothing is published (`PICKUP_HOURS`, or
  `SHOP_PICKUP_HOURS`, which the storefront pages already read; either one is enough). The address
  travels alone, and a buyer standing at a locked garage at midnight has been told nothing
  about when to come. Anything you write here is printed as you wrote it, on the
  order page and in the email — for example `Weekdays 09:00–20:00, Saturday 10:00–16:00`.
- **Is there something a person needs at the door?** Default: nothing (`PICKUP_NOTE`). One
  line, printed under the address: which door, which lane, where to park, whether to ring.
- **How many hours does a bay code work?** Default: 72 (`PICKUP_CODE_VALID_HOURS`). Three
  days was picked so a parcel that lands on a Friday is still collectable on Sunday; the
  number is a guess about how long you are willing to have a paid parcel sitting in the
  garage, and only you can settle it. The code stops working when the hours run out, and the
  buyer's order page then says the code expired and asks them to write to the shop.
- **Which clock do the shop's times print in?** Default: UTC, labelled `UTC`
  (`SHOP_TIMEZONE`). Every hour the shop prints to a customer — "the code works until
  2026-09-06 18:40" — is written with the zone beside it, so it cannot be misread. Set
  `SHOP_TIMEZONE=America/Toronto` and the same line prints Ottawa time with `EDT` or `EST`
  beside it. Nothing else changes.
- **How the code reaches the buyer, in this order.** When the packer puts the parcel in a
  bay, the shop mints a one-time code for that one bay and sends a fourth email — order
  number, bay, code, address, hours, and the hour the code stops working — in the language
  the buyer ordered in. The buyer's own order page carries the same block, so a customer who
  deleted the email has somewhere to look. While SMTP is unconfigured (`docs/OWNER-ACTIONS.md`, decision 3) no email
  leaves, the log records that the message was skipped and who it was for, the order page
  still shows the code, and the code is also handed back to the person packing the parcel,
  who is then the one who has to pass it on. **Without SMTP, somebody has to read the code to the
  customer.**
- **The code is readable until it is spent, and this is a deliberate trade.** The code is
  stored twice: as a slow salted hash, which is the only copy the door itself checks, and as
  the digits themselves, which is what the buyer's order page prints back to them. The second
  copy is erased the moment the code is used, the parcel leaves the bay, or the hours run
  out — an expired code kept its digits in the database until this was fixed, and the row
  is emptied now the first time anybody looks at that order. What it costs:
  somebody who can read the shop's database can read a live code — although the same person
  can already read the order number and the email address beside it, which is the whole of
  the proof the order page asks for, so the copy hands them nothing they could not fetch
  anyway. What it buys: a customer who lost the email can still collect their parcel. Say the
  word if you would rather the code lived only in the email, and the page stops printing it.
- **Every place a live code exists in plain digits, so you can count them.** The
  `locker_access` row in the shop's database, until the code is spent or withdrawn. The
  email in the buyer's mailbox, while SMTP is configured. The buyer's own order page. And
  the reply on the screen of the person who put the parcel in the bay, which is the copy
  they read out to a customer when there is no email. There was a fifth: with SMTP off the
  whole unsent message was written to the server log, code and all, on exactly the
  deployment where the shop cannot send mail. The log now keeps the recipient, the subject
  and the length, and the next bullet is the switch that governs the rest.
- **Guessing at the door is shut down the same way the courier's is.** Five wrong codes for
  one order inside fifteen minutes lock that order out for fifteen minutes, and fifteen wrong
  codes from one address lock the address out of both doors — the courier's and the buyer's.
  Every lockout appears on the exception list with the address that caused it. An operator
  lifts one with `POST /v1/pickup-access/<order number>/unlock`. The numbers are the
  `COURIER_PIN_*` settings from section 1; both doors read them.
- **A code that has run out is re-issued by hand, and somebody has to be told to do it.**
  Nothing re-mints a code on its own. An operator calls
  `POST /v1/packages/<package id>/pickup-code`, and that one call withdraws whatever the
  buyer was holding, mints a code for the bay the parcel is actually in, hands the digits
  back on the screen the way assigning a bay does, and sends the "your parcel is in the
  locker" email again in the buyer's language. The buyer's own page carries the new code
  the moment it exists, and the old one opens nothing. Two things to settle: who is allowed
  to press it — today it is the operator key, the same key that assigns bays — and how a
  customer asks. The order page, the FAQ and the shipping page all tell them to write to
  the shop, so somebody has to be reading that mailbox and making this call. Assigning the
  same bay a second time answers 409, because the parcel is already in it; that refusal is
  what made this route necessary.
- **A bay is emptied as one event.** When the door is closed and re-locked and an operator
  completes the handoff, everything that was in that bay is recorded as gone. With one parcel
  per bay — how the garage is used today — this is exactly right. If you ever put two orders
  in one bay, one of them being collected marks the other as collected too.
- **A pickup order that reaches a bay while the address is empty gets no code at all.** It
  lands on the exception list instead, saying which order it was and that `PICKUP_ADDRESS`
  needs setting. Nothing is sent to the buyer, because digits with no building is a message
  that cannot be acted on. Set the address, then call
  `POST /v1/packages/<package id>/pickup-code` for that parcel: the code is minted, the
  email goes out, and the alert closes itself. (This used to say "assign the bay again",
  which the software refuses for a parcel already sitting in one.)
- **What an unsent email leaves in the server log.** Default: the address it was for, the
  subject, and how many characters long it was — enough for an operator to see that the
  shop tried to write to somebody and what about. Set `MAIL_LOG_BODIES=true` and the text
  of the message is written as well, which is useful while you are setting the shop up and
  reading what a customer would have received. A one-time locker code never travels with
  it: the code is cut out of the text before the line is written, in both languages, and a
  message that still carries one after that is withheld whole. Turning the flag on is
  therefore safe for the code and loose with everything else the message says — names,
  addresses, what somebody bought — so leave it off on a machine other people can read.
- **The buyer's door gives one answer to every refusal, and the courier's does not.** Type
  a wrong code, an expired code, a code that was already used, or an order number that was
  never issued, and the reply is the same sentence every time: this code does not open a
  bay, check the number and the code on your order page, write to the shop if it expired.
  The door is on the open internet and its first field is an order number, so an answer
  that varied would let somebody feed it guesses and learn which orders exist and which
  codes are live. The real reason is written to the shop's log every time, and into the
  alert on the exception list when a lockout trips, so an operator helping a customer on
  the phone can still see what happened. The courier's door keeps its plain answers —
  "PIN outside pickup window" tells a driver standing at the locker what to do next, and
  that door asks for a pickup identifier the shop handed out rather than an order number
  a stranger can guess.
- **An address needs a street before the shop will sell pickup.** `SHOP_PICKUP_ADDRESS_JSON`
  is filled in field by field, and a copy of it holding only a city used to be enough to
  switch pickup on — the shop would have sold "collect it in Ottawa" and minted codes for
  a building nobody had named. A street line is required now; a city, a province and a
  postal code without one read as no address at all, and pickup stays off. The same guard
  is why a bag priced for pickup in a shop with no address is quoted with shipping on it:
  the price a shopper sees is the price of what the order will have to become.
- **The address and the hours print in the language you typed them.** The shop is bilingual
  and the locker is one place, so the street address is printed as written on both the
  English and the Ukrainian pages — which is right for an address, because that is what the
  street sign and the courier's label say. The opening hours are the one line worth writing
  twice: `SHOP_PICKUP_HOURS_UK` is their Ukrainian rendering, and the Ukrainian
  FAQ, shipping page and order page print it in place of `PICKUP_HOURS`. One place still
  prints the English string on the Ukrainian page — the single grey line under the pickup
  option at checkout, which is drawn in the browser and cannot reach that setting; it is a
  hint before the order rather than the instruction you follow at the door, and closing the
  gap is a small change to make when the Ukrainian hours are actually set. There is no
  second setting for the door note (`PICKUP_NOTE`) either; a Ukrainian buyer reads it in the
  language you wrote it in. Say the word if you want one and it is added.
