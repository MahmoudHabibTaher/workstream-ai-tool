// Repo text is text (plan T2): Swing reads a string starting `<html>` as markup, and a
// notification's content is always HTML. Every tooltip, dialog message and notification body is
// built here, with the text escaped; markup comes only from this file's own constants.
package dev.workstream.jetbrains

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.text.HtmlChunk

object Text {
    const val GROUP = "Workstreams"

    /** Text for a sink that is always HTML, such as a notification's content. */
    fun escaped(text: String): String = HtmlChunk.text(text).toString()

    /** Text for a sink that turns markup on when it sees `<html>`, such as a tooltip. */
    fun html(text: String): String = HtmlChunk.text(text).wrapWith("html").toString()

    fun notify(project: Project, text: String, type: NotificationType = NotificationType.WARNING) {
        NotificationGroupManager.getInstance().getNotificationGroup(GROUP)
            .createNotification(escaped(text), type)
            .notify(project)
    }
}
