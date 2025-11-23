import { useState } from "react";
import axios from "axios";

export default function AiSeoTool() {
    const [content, setContent] = useState("");
    const [seoData, setSeoData] = useState(null);
    const [metaDescription, setMetaDescription] = useState("");
    const [seoSuggestions, setSeoSuggestions] = useState("");
    const [loading, setLoading] = useState(false);

    const analyzeSeo = async () => {
        setLoading(true);
        try {
            const response = await axios.post("http://localhost:8000/analyze_seo/", { content });
            setSeoData(response.data);
        } catch (error) {
            console.error("SEO Analysis Error: ", error);
        }
        setLoading(false);
    };

    const generateMeta = async () => {
        setLoading(true);
        try {
            const response = await axios.post("http://localhost:8000/generate_meta/", { content });
            setMetaDescription(response.data.meta_description);
        } catch (error) {
            console.error("Meta Description Error: ", error);
        }
        setLoading(false);
    };

    const getSeoSuggestions = async () => {
        setLoading(true);
        try {
            const response = await axios.post("http://localhost:8000/suggest_improvements/", { content });
            setSeoSuggestions(response.data.seo_suggestions);
        } catch (error) {
            console.error("SEO Suggestions Error: ", error);
        }
        setLoading(false);
    };

    return (
        <div className="container mx-auto p-6">
            <h1 className="text-2xl font-bold mb-4">AI SEO Optimization Tool</h1>
            <textarea
                className="w-full p-2 border rounded"
                rows="6"
                placeholder="Enter your content here..."
                value={content}
                onChange={(e) => setContent(e.target.value)}
            ></textarea>
            <div className="flex space-x-4 mt-4">
                <button className="px-4 py-2 bg-blue-500 text-white rounded" onClick={analyzeSeo}>
                    Analyze SEO
                </button>
                <button className="px-4 py-2 bg-green-500 text-white rounded" onClick={generateMeta}>
                    Generate Meta Description
                </button>
                <button className="px-4 py-2 bg-purple-500 text-white rounded" onClick={getSeoSuggestions}>
                    Get SEO Suggestions
                </button>
            </div>
            {loading && <p className="mt-4">Processing...</p>}
            {seoData && (
                <div className="mt-6 p-4 border rounded">
                    <h2 className="text-xl font-bold">SEO Analysis</h2>
                    <p><strong>Word Count:</strong> {seoData.word_count}</p>
                    <p><strong>Readability Score:</strong> {seoData.readability}</p>
                    <p><strong>Top Keywords:</strong> {seoData.top_keywords.join(", ")}</p>
                    <h3 className="mt-4 font-bold">Keyword Densities:</h3>
                    <ul>
                        {Object.entries(seoData.keyword_densities).map(([keyword, density]) => (
                            <li key={keyword}><strong>{keyword}:</strong> {density}%</li>
                        ))}
                    </ul>
                </div>
            )}
            {metaDescription && (
                <div className="mt-6 p-4 border rounded">
                    <h2 className="text-xl font-bold">Generated Meta Description</h2>
                    <p>{metaDescription}</p>
                </div>
            )}
            {seoSuggestions && (
                <div className="mt-6 p-4 border rounded">
                    <h2 className="text-xl font-bold">SEO Improvement Suggestions</h2>
                    <p>{seoSuggestions}</p>
                </div>
            )}
        </div>
    );
}
