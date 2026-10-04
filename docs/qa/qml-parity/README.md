# Native desktop layout restoration

Reviewed the latest fetched origin/main (2b1543a) and the QML SettingsView
history, especially 0fabab4 and 5d10add. The native GTK migration had flattened
its layout into full-width buttons and ungrouped fields. This change restores
its fixed branded sidebar, page headings, apricot welcome card, paired model
and shortcut cards, bounded buttons and grouped form sections using the new
white/sky/apricot palette. It keeps GTK and the existing backend operations.

Home and shared UI components are separate modules. Model installation now
provides a file chooser and an expandable custom catalog section. Its exclusive
installation lease prevents a second click from resetting cancellation on an
active download. Device invitations remain hidden until generated. No account
or Firebase controls have been restored.

Verification: native GTK release build passed; Xvfb smoke constructed all five
pages and switched to Settings. The Home screenshot was inspected at 920×680
using a disposable copy of the example config. Real Wayland, smaller-window
interaction and the remaining pages need further visual/device checks. Android
and the website were not changed in this desktop-specific restoration.
