# Architecture

Core engine never depends on game plugins.
Games communicate through SDK interfaces.
Use dependency injection, event bus and configuration-driven design.