from docling.document_converter import DocumentConverter
from utils.sitemap import get_sitemap_urls

converter = DocumentConverter()

# --------------------------------------------------------------
# Basic PDF extraction
# --------------------------------------------------------------

result = converter.convert("https://arxiv.org/pdf/2408.09869")

document = result.document
markdown_output = document.export_to_markdown()
json_output = document.export_to_dict()

print(markdown_output)

# --------------------------------------------------------------
# Basic HTML extraction
# --------------------------------------------------------------

result = converter.convert("https://ds4sd.github.io/docling/")

document = result.document
markdown_output = document.export_to_markdown()
print(markdown_output)

# --------------------------------------------------------------
# Scrape multiple pages from the provided URLs
# --------------------------------------------------------------

urls = [
    "https://www.nhs.uk/pregnancy/keeping-well/have-a-healthy-diet/",
    "https://www.unicef.org/parenting/child-development/what-to-eat-when-pregnant",
    "https://www.unicef.org/parenting/pregnancy-milestones/first-trimester#baby-growth",
    "https://www.unicef.org/parenting/pregnancy-milestones/second-trimester",
    "https://www.unicef.org/parenting/pregnancy-milestones/third-trimester",
    "https://www.unicef.org/bangladesh/parenting-bd/your-first-trimester-guide",
    "https://www.unicef.org/bangladesh/parenting-bd/your-second-trimester-guide",
    "https://www.unicef.org/bangladesh/parenting-bd/your-third-trimester-guide"
]

conv_results_iter = converter.convert_all(urls)

docs = []
for result in conv_results_iter:
    if result.document:
        document = result.document
        docs.append(document)
