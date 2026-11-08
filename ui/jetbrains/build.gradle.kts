// The Workstreams plugin for IntelliJ IDEA and Android Studio. It compiles against IntelliJ IDEA
// 2026.2 (build 262), the older of the two platforms it targets, and verifies against the local
// installs of both (plan T1). Every fact it shows comes from the ws CLI (Cli.kt).
import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    id("org.jetbrains.kotlin.jvm") version "2.3.20"
    id("org.jetbrains.intellij.platform") version "2.19.0"
}

group = "dev.workstream"
version = "0.1.0"

val platformVersion = "2026.2.4"
val home: String = System.getProperty("user.home")
val localIdea = providers.gradleProperty("localIdea").orElse("$home/Applications/IntelliJ IDEA.app")
val localStudio = providers.gradleProperty("localStudio").orElse("$home/Applications/Android Studio.app")
// The checkout this plugin sits in: its `src` holds the CLI the tests must run (plan T4).
val checkout = layout.projectDirectory.dir("../..").asFile.canonicalFile

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

kotlin {
    jvmToolchain {
        languageVersion = JavaLanguageVersion.of(25)
        vendor = JvmVendorSpec.JETBRAINS
    }
}

dependencies {
    intellijPlatform {
        intellijIdea(platformVersion)
        bundledPlugin("org.jetbrains.plugins.terminal")
        testFramework(TestFrameworkType.Platform)
    }
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.opentest4j:opentest4j:1.3.0")
}

intellijPlatform {
    buildSearchableOptions = false
    pluginConfiguration {
        ideaVersion {
            sinceBuild = "262"
            untilBuild = provider { null }
        }
    }
    pluginVerification {
        ides {
            local(file(localIdea.get()))
            local(file(localStudio.get()))
        }
    }
}

tasks.test {
    // The branch's CLI, never the ws on PATH, which runs main's code (plan T4). The headless tests
    // put this argv in the wsCommand setting.
    environment("PYTHONPATH", checkout.resolve("src").path)
    // The CLI is an input, so a change to it reruns the tests rather than reusing the last result.
    inputs.dir(checkout.resolve("src/workstream")).withPropertyName("cli")
    environment("WS_TEST_COMMAND", """["python3", "-B", "-m", "workstream"]""")
    environment("GIT_AUTHOR_NAME", "test")
    environment("GIT_AUTHOR_EMAIL", "test@example.com")
    environment("GIT_COMMITTER_NAME", "test")
    environment("GIT_COMMITTER_EMAIL", "test@example.com")
}

// The 262 IDE's ultimate-features plugin has a startup activity that can't be built in a light
// test project, which fails every headless test. The plugin uses nothing from it.
tasks.prepareTestSandbox {
    disabledPlugins.add("com.intellij.modules.ultimate")
}
