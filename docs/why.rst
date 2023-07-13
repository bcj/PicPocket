Why PicPocket?
==============

PicPocket is born out of the frustration that Apple's *Photos* application forces you to store your photos in a database, and requires you to export those photos if you want to access them from outside *Photos*.
It is likewise born out of a distrust in Google *Photos*, as it wants you to store your photos on their servers and limit how you can access the original files.

The goal of PicPocket is to make it easier for you to manage your own photos, letting them exist as regular files on your computer, without you needing to cede control of them.
PicPocket provides tools for tagging and searching through your photos, and for transferring photos from your camera to your computer in an orderly fashion.

What is PicPocket?
------------------

PicPocket is a database that stores metadata about your photos.
This information contains descriptions, alt text, and ratings for photos, as well as a nested tagging structure that makes it easier to find what you're looking for.

PicPocket also provides functionality for copying new photos from your camera to your computer—allowing you to automatically store them by type and date.

PicPocket provides an API for searching through your photos, and fetching image files based on criteria, so it can be used programmatically.

What PicPocket isn't (Yet, and What it Will Never Be)
-----------------------------------------------------

First and foremost, PicPocket is not commercial-grade software.
This is hobby software being written by one person in their spare time.
PicPocket's features and functionality are limited by both what I have the time and interest in developing, and in what I am comfortable maintaining.
This is software that I am entrusting with my own photos, so you can rest assured that all code will be thoroughly tested prior to release, and that any potentially-destructive action will err on the safest default (e.g., PicPocket will refuse to overwrite a photo on import, and defaults to leaving the file when an image is removed from the database).
But this means that the UI will be clunkier than commercial software, updates will be smaller and less frequent, and that good feature requests may be rejected.

PicPocket does not offer machine-learning-based suggested tags for photos.
The only suggestions that PicPocket offers are opt-in, and solely based on your own tagging (optionally, PicPocket will suggest tags that you've applied to images in that batch).
PicPocket does not collect or share information about what photos you store in it, metadata you create for photos (such as tags or descriptions), or how you use PicPocket.
Anything you do with PicPocket will stay within your local setup.

PicPocket is not a photo editing tool.
It's unlikely that it will ever provide even the most-basic of editing controls.
It may one day provide hooks for quickly opening up images in image editors, and its API means you could use it as part of your own pipeline for editing photos.

PicPocket is not a photo backup tool.
One of the many reasons PicPocket has you store your photos as regular files, is so that you can use whatever backup utilities you prefer to keep your photos safe.
Hooks for backing up your photos on external devices (or remote servers) may one day be added—even then, the official PicPocket stance will be to use professionally vetted backup utilities either instead or as well.

PicPocket is not multi-user software.
It is not built for keeping track of millions of photos (at time of writing, it has been built to manage ~50k photos).
It is written with the assumption that people would each have their own PicPocket database.
As such, permissions for PicPocket are all-or-nothing.

PicPocket is not yet lock-in free.
While your images are immediately usable in another application, your tags are not.
Image tags can be exported to a file (or accessed programmatically), but no utilities are provided for adding those tags to other programs.
PicPocket also is built on the assumption that you will use it to copy images from your devices to your photos directory.
While it is possible to skip this, by re-importing a destination, that process is slow.